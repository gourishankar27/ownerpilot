from functools import lru_cache
from pathlib import Path
from contextvars import ContextVar
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class RfqSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="RFQ_", env_file=".env", extra="ignore"
    )
    auth_secret: str = ""
    storage_root: Path = Path(".local/rfq/documents")
    max_file_bytes: int = Field(20 * 1024 * 1024, ge=1024, le=100 * 1024 * 1024)
    max_documents: int = Field(10, ge=1, le=50)
    max_pages: int = Field(50, ge=1, le=200)
    max_rows: int = Field(10000, ge=1, le=50000)
    max_columns: int = Field(100, ge=1, le=500)
    max_sheets: int = Field(20, ge=1, le=100)
    max_uncompressed_bytes: int = 80 * 1024 * 1024
    max_text_chars: int = 500000
    ocr_command: str = "tesseract"
    ocr_language: str = "eng"
    ocr_timeout: int = 60
    ocr_strategy: str = "enhanced-v2"
    ocr_dpi: int = Field(300, ge=144, le=400)
    ocr_max_pixels: int = Field(24000000, ge=1000000, le=32000000)
    ocr_max_passes: int = Field(8, ge=1, le=20)
    ocr_max_regions: int = Field(5, ge=0, le=10)
    ocr_max_words: int = Field(12000, ge=100, le=30000)
    extraction_policy: str = "selective-v2"
    max_model_calls: int = Field(8, ge=1, le=40)
    max_routing_blocks: int = Field(250, ge=10, le=1000)
    redis_url: str = "redis://127.0.0.1:6380/0"
    ollama_url: str = "http://localhost:11434"
    ollama_model: str = ""
    model_timeout: float = Field(180, ge=1, le=600)
    model_input_chars: int = Field(12000, ge=500, le=24000)
    model_output_tokens: int = Field(4096, ge=128, le=8192)
    model_context: int = Field(16384, ge=2048, le=32768)
    model_temperature: float = Field(0, ge=0, le=1)
    model_retries: int = Field(1, ge=0, le=2)
    model_keep_alive_seconds: int = Field(300, ge=0, le=3600)
    compact_prompt_version: str = "extract_v3"
    model_schema_profile: Literal["full", "compact"] = "full"
    max_metadata_bytes: int = Field(4 * 1024 * 1024, ge=1024, le=16 * 1024 * 1024)
    max_chunks: int = Field(40, ge=1, le=100)
    job_timeout: int = Field(1800, ge=60, le=7200)
    max_attempts: int = Field(3, ge=1, le=5)


@lru_cache
def _cached_settings() -> RfqSettings:
    return RfqSettings()


_active: ContextVar[RfqSettings | None] = ContextVar("rfq_configuration", default=None)


def settings() -> RfqSettings:
    return _active.get() or _cached_settings()


settings.cache_clear = _cached_settings.cache_clear

PROCESSING_KEYS = (
    "ocr_strategy",
    "ocr_dpi",
    "ocr_max_passes",
    "ocr_max_regions",
    "ocr_language",
    "ollama_model",
    "model_context",
    "model_output_tokens",
    "model_timeout",
    "model_input_chars",
    "max_model_calls",
    "model_retries",
    "compact_prompt_version",
    "model_schema_profile",
)


def activate(configuration: dict):
    values = settings().model_dump()
    values.update({k: v for k, v in configuration.items() if k in PROCESSING_KEYS})
    return _active.set(RfqSettings.model_validate(values))


def deactivate(token):
    _active.reset(token)
