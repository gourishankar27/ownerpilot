import math
import os
from urllib.parse import urlparse

import httpx


class Embeddings:
    dimension = 768
    preprocessing = "nomic-prefixed-specs/1"

    def __init__(self, transport=None):
        self.model = os.environ.get("CATALOG_EMBED_MODEL", "nomic-embed-text:v1.5")
        self.url = os.environ.get("CATALOG_EMBED_URL", "http://localhost:11434").rstrip(
            "/"
        )
        parsed = urlparse(self.url)
        if (
            parsed.scheme != "http"
            or parsed.hostname
            not in {"localhost", "127.0.0.1", "host.docker.internal", "ollama"}
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.path
        ):
            raise ValueError("Local embedding endpoint required")
        self.client = httpx.Client(timeout=120, trust_env=False, transport=transport)

    def health(self):
        response = self.client.get(self.url + "/api/tags")
        response.raise_for_status()
        tag = next(
            (t for t in response.json()["models"] if t["name"] == self.model), None
        )
        if not tag or tag.get("remote_host") or tag.get("remote_model"):
            raise ValueError("Configured local embedding model unavailable")
        return {
            "model": self.model,
            "digest": tag["digest"],
            "dimension": self.dimension,
            "preprocessing": self.preprocessing,
        }

    def encode(self, texts, *, query=False, digest=None):
        if not 1 <= len(texts) <= 32 or any(
            not t.strip() or len(t.encode()) > 2000 for t in texts
        ):
            raise ValueError("Embedding batch/input limit")
        before = self.health()
        if digest and before["digest"] != digest:
            raise ValueError("Embedding model digest changed; rebuild index")
        prefix = "search_query: " if query else "search_document: "
        error = None
        for _ in range(2):
            try:
                with self.client.stream(
                    "POST",
                    self.url + "/api/embed",
                    json={
                        "model": self.model,
                        "input": [prefix + t for t in texts],
                        "truncate": False,
                        "keep_alive": "5m",
                    },
                ) as response:
                    response.raise_for_status()
                    raw = bytearray()
                    for part in response.iter_bytes():
                        raw.extend(part)
                        if len(raw) > 4 * 1024 * 1024:
                            raise ValueError("Embedding response limit")
                import json

                data = json.loads(raw)
                if data.get("model") != self.model or len(data["embeddings"]) != len(
                    texts
                ):
                    raise ValueError("Embedding identity/count mismatch")
                vectors = []
                for vector in data["embeddings"]:
                    if len(vector) != self.dimension or any(
                        isinstance(v, bool)
                        or not isinstance(v, (int, float))
                        or not math.isfinite(v)
                        for v in vector
                    ):
                        raise ValueError("Embedding dimension/nonfinite output")
                    norm = math.sqrt(sum(v * v for v in vector))
                    if norm < 1e-12:
                        raise ValueError("Zero embedding")
                    vectors.append([v / norm for v in vector])
                if self.health()["digest"] != before["digest"]:
                    raise ValueError("Embedding model changed during request")
                return vectors
            except httpx.HTTPError as exc:
                error = exc
        raise RuntimeError("Local embedding request failed") from error
