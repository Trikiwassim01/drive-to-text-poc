
from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    google_api_key: str | None = None
    max_file_size_mb: int = 25
    max_files_per_batch: int = 50
    batch_concurrency: int = 2
    ocr_dpi: int = 200
    pdf_min_chars_per_page: int = 20
    http_timeout_s: float = 30.0

    @field_validator("google_api_key")
    @classmethod
    def _blank_key_is_none(cls, value: str | None) -> str | None:
        return value.strip() or None if value else None

    @property
    def max_file_bytes(self) -> int:
        return self.max_file_size_mb * 1024 * 1024


@lru_cache
def get_settings() -> Settings:
    return Settings()
