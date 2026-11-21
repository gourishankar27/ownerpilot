from __future__ import annotations

import asyncio
import time
from pathlib import Path
from typing import Protocol
from urllib.parse import urlparse

import httpx
from pydantic import ValidationError

from .config import settings
from .contracts import Block, Proposal, CompactProposal

PROMPT_VERSION = "extract_v1"
PROMPT = (Path(__file__).parent / "prompts" / "extract_v1.txt").read_text(
    encoding="utf-8"
)


class ProviderError(RuntimeError):
    def __init__(self, category: str, retryable: bool = False):
        super().__init__(category)
        self.category = category
        self.retryable = retryable


class Provider(Protocol):
    async def extract(self, blocks: list[Block]) -> tuple[Proposal, dict]: ...


class OllamaProvider:
    def __init__(
        self,
        transport: httpx.AsyncBaseTransport | None = None,
        *,
        model: str | None = None,
        compact: bool = False,
    ):
        self.cfg = (
            settings().model_copy(update={"ollama_model": model})
            if model
            else settings()
        )
        self.compact = compact
        self.prompt_version = (
            self.cfg.compact_prompt_version if compact else PROMPT_VERSION
        )
        self.prompt = (
            (
                Path(__file__).parent / "prompts" / (self.prompt_version + ".txt")
            ).read_text(encoding="utf-8")
            if compact
            else PROMPT
        )
        self.transport = transport
        parsed = urlparse(self.cfg.ollama_url)
        # Prevent accidentally forwarding private documents to an external endpoint.
        if (
            parsed.scheme != "http"
            or parsed.hostname
            not in {"localhost", "127.0.0.1", "::1", "host.docker.internal", "ollama"}
            or parsed.username
            or parsed.password
        ):
            raise ProviderError("local_provider_url_required")

    async def health(self) -> dict:
        try:
            async with httpx.AsyncClient(
                timeout=5, transport=self.transport, trust_env=False
            ) as client:
                response = await client.get(self.cfg.ollama_url + "/api/tags")
                response.raise_for_status()
                models = response.json()["models"]
            model = next(
                (m for m in models if m["name"] == self.cfg.ollama_model), None
            )
            if not model or model.get("remote_host") or model.get("remote_model"):
                return {
                    "available": False,
                    "reason": "Configure RFQ_OLLAMA_MODEL with an installed local model tag.",
                }
            return {
                "available": True,
                "model": model["name"],
                "digest": model.get("digest"),
                "size": model.get("size"),
            }
        except (httpx.HTTPError, ValueError, KeyError):
            return {"available": False, "reason": "Local Ollama is unavailable."}

    async def extract(self, blocks: list[Block]) -> tuple[Proposal, dict]:
        import json

        started = time.perf_counter()

        health = await self.health()
        if not health["available"]:
            raise ProviderError("model_unavailable", True)
        payload = json.dumps(
            [
                {
                    "block_id": b.id,
                    "text": b.text,
                    **(
                        {"columns": b.metadata.get("table_columns"), "cells": b.cells}
                        if self.compact and b.cells
                        else {}
                    ),
                }
                for b in blocks
            ],
            ensure_ascii=False,
        )
        if sum(len(b.text) for b in blocks) > self.cfg.model_input_chars:
            raise ProviderError("model_input_limit")
        # UTF-8 bytes give a conservative upper bound without introducing a second
        # tokenizer/model dependency. Reserve output and message-template headroom.
        if (
            len((self.prompt + payload).encode("utf-8"))
            + self.cfg.model_output_tokens
            + 256
            > self.cfg.model_context
        ):
            raise ProviderError("model_context_budget_exceeded")
        body = {
            "model": self.cfg.ollama_model,
            "stream": False,
            "think": False,
            "format": (
                CompactProposal if self.compact else Proposal
            ).model_json_schema(),
            "keep_alive": self.cfg.model_keep_alive_seconds,
            "messages": [
                {"role": "system", "content": self.prompt},
                {"role": "user", "content": "UNTRUSTED_DOCUMENT_BLOCKS\n" + payload},
            ],
            "options": {
                "temperature": self.cfg.model_temperature,
                "num_ctx": self.cfg.model_context,
                "num_predict": self.cfg.model_output_tokens,
            },
        }
        for attempt in range(self.cfg.model_retries + 1):
            try:
                async with httpx.AsyncClient(
                    timeout=self.cfg.model_timeout,
                    transport=self.transport,
                    trust_env=False,
                ) as client:
                    async with client.stream(
                        "POST", self.cfg.ollama_url + "/api/chat", json=body
                    ) as response:
                        response.raise_for_status()
                        raw = bytearray()
                        async for part in response.aiter_bytes():
                            raw.extend(part)
                            if len(raw) > 1024 * 1024:
                                raise ProviderError("model_response_limit")
                    data = json.loads(raw)
                if (
                    data.get("model") != self.cfg.ollama_model
                    or data.get("done") is not True
                    or data.get("done_reason") == "length"
                ):
                    raise ProviderError("model_incomplete_or_identity_mismatch")
                conflicts = []
                if self.compact:
                    compact = CompactProposal.model_validate_json(
                        data["message"]["content"]
                    )
                    index = {b.id: b for b in blocks}

                    def field(value, source):
                        block = index.get(source)
                        return {
                            "value": value,
                            "block_id": source,
                            "excerpt": block.text
                            if block and value is not None and value in block.text
                            else None,
                        }

                    header = {}
                    for entry in compact.header:
                        if (
                            entry.field in header
                            and header[entry.field]["value"] != entry.value
                        ):
                            conflicts.append(entry.field)
                        else:
                            header[entry.field] = field(entry.value, entry.source)
                    proposal = Proposal.model_validate(
                        {
                            "header": header,
                            "items": [
                                {
                                    name: field(value, row.source)
                                    for name, value in row.values.model_dump().items()
                                    if value is not None
                                }
                                for row in compact.items
                            ],
                        }
                    )
                else:
                    proposal = Proposal.model_validate_json(data["message"]["content"])
                metadata = {
                    k: data[k]
                    for k in (
                        "prompt_eval_count",
                        "eval_count",
                        "load_duration",
                        "prompt_eval_duration",
                        "eval_duration",
                        "total_duration",
                    )
                    if k in data
                }
                return proposal, {
                    "provider": "ollama",
                    "model": self.cfg.ollama_model,
                    "digest": health.get("digest"),
                    "prompt_version": self.prompt_version,
                    "schema_profile": "compact-source-row/v2"
                    if self.compact
                    else "phase1-full/v1",
                    "header_conflicts": conflicts,
                    "call_duration_ms": (time.perf_counter() - started) * 1000,
                    "input_chars": len(payload),
                    "tokens_per_second": data.get("eval_count", 0)
                    / (data["eval_duration"] / 1e9)
                    if data.get("eval_duration", 0) > 0
                    else None,
                    "attempt": attempt + 1,
                    "runtime": metadata,
                    "options": body["options"],
                }
            except httpx.TimeoutException as exc:
                error = ProviderError("model_timeout", True)
                cause = exc
            except httpx.HTTPError as exc:
                error = ProviderError("model_connection_or_http_error", True)
                cause = exc
            except (ValidationError, ValueError, KeyError, TypeError) as exc:
                error = ProviderError("invalid_structured_output")
                cause = exc
            if attempt == self.cfg.model_retries:
                raise error from cause
            await asyncio.sleep(0.25 * (attempt + 1))
        raise ProviderError("model_failure")
