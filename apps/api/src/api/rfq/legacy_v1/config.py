from functools import lru_cache
from pathlib import Path

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
    redis_url: str = "redis://127.0.0.1:6380/0"
    ollama_url: str = "http://localhost:11434"
    ollama_model: str = ""
    model_timeout: float = Field(180, ge=1, le=600)
    model_input_chars: int = Field(12000, ge=500, le=24000)
    model_output_tokens: int = Field(4096, ge=128, le=8192)
    model_context: int = Field(16384, ge=2048, le=32768)
    model_temperature: float = Field(0, ge=0, le=1)
    model_retries: int = Field(1, ge=0, le=2)
    max_chunks: int = Field(40, ge=1, le=100)
    job_timeout: int = Field(1800, ge=60, le=7200)
    max_attempts: int = Field(3, ge=1, le=5)


@lru_cache
def settings() -> RfqSettings:
    return RfqSettings()
