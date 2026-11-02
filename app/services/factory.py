"""Build the transcription provider selected by settings."""

from app.config import Settings
from app.services.errors import ProviderConfigError
from app.services.transcription.base import TranscriptionProvider
from app.services.transcription.fake import FakeTranscriptionProvider
from app.services.transcription.faster_whisper import FasterWhisperTranscriptionProvider
from app.services.transcription.openai_whisper import OpenAITranscriptionProvider


def build_transcription_provider(settings: Settings) -> TranscriptionProvider:
    """Return the provider named by ``TRANSCRIPTION_PROVIDER``."""
    provider = settings.transcription_provider
    if provider == "fake":
        return FakeTranscriptionProvider()
    if provider == "openai":
        api_key = settings.openai_api_key_value()
        if not api_key:
            raise ProviderConfigError(
                "OPENAI_API_KEY is required when TRANSCRIPTION_PROVIDER is 'openai'."
            )
        return OpenAITranscriptionProvider(
            api_key=api_key,
            base_url=settings.openai_base_url,
            model=settings.openai_transcription_model,
            timeout=settings.openai_timeout_seconds,
        )
    if provider == "faster_whisper":
        return FasterWhisperTranscriptionProvider(
            model_size=settings.faster_whisper_model,
            device=settings.faster_whisper_device,
            compute_type=settings.faster_whisper_compute_type,
        )
    raise ProviderConfigError(f"Unsupported transcription provider: {provider}")
