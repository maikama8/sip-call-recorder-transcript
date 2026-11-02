"""Environment-backed settings."""

from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

TranscriptionProviderName = Literal["fake", "openai", "faster_whisper"]


class Settings(BaseSettings):
    """Runtime configuration loaded from the environment and an optional ``.env``."""

    app_name: str = "SIP Call Recorder"
    transcription_provider: TranscriptionProviderName = "fake"
    openai_api_key: SecretStr | None = None
    openai_base_url: str = Field(default="https://api.openai.com/v1", min_length=1)
    openai_transcription_model: str = Field(default="whisper-1", min_length=1)
    openai_timeout_seconds: float = Field(default=60.0, gt=0)
    faster_whisper_model: str = Field(default="base", min_length=1)
    faster_whisper_device: str = Field(default="cpu", min_length=1)
    faster_whisper_compute_type: str = Field(default="int8", min_length=1)
    database_url: str = Field(default="sqlite:///./data/calls.db", min_length=1)
    recordings_dir: str = Field(default="./data/recordings", min_length=1)
    monitor_dir: str = ""
    cdr_path: str = ""
    watch_enabled: bool = False
    watch_interval_seconds: float = Field(default=5.0, gt=0)
    watch_settle_seconds: float = Field(default=5.0, ge=0)
    max_upload_bytes: int = Field(default=25 * 1024 * 1024, gt=0)
    default_language: str = Field(default="en", min_length=1, max_length=16)

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @field_validator("transcription_provider", mode="before")
    @classmethod
    def _normalize_provider(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip().lower()
        return value

    @field_validator("default_language")
    @classmethod
    def _normalize_language(cls, value: str) -> str:
        return value.strip().lower()

    def openai_api_key_value(self) -> str | None:
        """Return the OpenAI key, or None when it is unset or blank."""
        if self.openai_api_key is None:
            return None
        value = self.openai_api_key.get_secret_value().strip()
        return value or None


@lru_cache
def get_settings() -> Settings:
    return Settings()
