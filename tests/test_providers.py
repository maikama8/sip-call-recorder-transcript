"""Provider selection and the OpenAI HTTP adapter."""

import httpx
import pytest
from pydantic import ValidationError

from app.main import create_app
from app.services.errors import ProviderConfigError, ProviderError
from app.services.factory import build_transcription_provider
from app.services.transcription.fake import FakeTranscriptionProvider
from app.services.transcription.faster_whisper import FasterWhisperTranscriptionProvider
from app.services.transcription.openai_whisper import OpenAITranscriptionProvider
from tests.conftest import build_settings


def test_factory_defaults_to_the_fake_provider(tmp_path) -> None:
    provider = build_transcription_provider(build_settings(tmp_path))
    assert provider.name == "fake"


def test_openai_provider_requires_an_api_key(tmp_path) -> None:
    settings = build_settings(tmp_path, transcription_provider="openai", openai_api_key=None)
    with pytest.raises(ProviderConfigError, match="OPENAI_API_KEY"):
        build_transcription_provider(settings)
    with pytest.raises(ProviderConfigError, match="OPENAI_API_KEY"):
        create_app(settings)


def test_provider_name_is_normalized(tmp_path) -> None:
    settings = build_settings(tmp_path, transcription_provider=" OpenAI ", openai_api_key="sk-test")
    assert settings.transcription_provider == "openai"
    assert build_transcription_provider(settings).name == "openai"


def test_unknown_provider_is_rejected(tmp_path) -> None:
    with pytest.raises(ValidationError):
        build_settings(tmp_path, transcription_provider="nope")


def test_fake_audio_returns_the_bundled_call() -> None:
    transcript = FakeTranscriptionProvider().transcribe("call.wav", b"\x00\x01not-text", None)
    assert transcript.provider == "fake"
    assert "invoice 1842" in transcript.text
    assert transcript.segments[0].speaker == "caller"
    assert transcript.notice is not None
    assert "does not decode audio" in transcript.notice


def test_fake_text_uses_the_upload_not_the_sample() -> None:
    transcript = FakeTranscriptionProvider().transcribe("notes.txt", b"caller: Hello there.", "en")
    assert transcript.text == "Hello there."
    assert transcript.language == "en"
    assert transcript.segments[0].speaker == "caller"
    assert transcript.notice is not None
    assert "text file" in transcript.notice


def test_openai_transcription_parses_verbose_json(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    class FakeResponse:
        status_code = 200
        text = ""

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return {
                "text": " Hello team. ",
                "language": "english",
                "duration": 3.5,
                "segments": [
                    {"start": 0.0, "end": 1.2, "text": " Hello"},
                    {"start": 1.2, "end": 3.5, "text": " team."},
                ],
            }

    class FakeClient:
        def __init__(self, *args: object, **kwargs: object) -> None:
            del args, kwargs

        def __enter__(self) -> "FakeClient":
            return self

        def __exit__(self, *args: object) -> bool:
            return False

        def post(self, url: str, **kwargs: object) -> FakeResponse:
            captured["url"] = url
            captured["data"] = kwargs["data"]
            captured["files"] = kwargs["files"]
            captured["headers"] = kwargs["headers"]
            return FakeResponse()

    monkeypatch.setattr(httpx, "Client", FakeClient)
    provider = OpenAITranscriptionProvider(
        api_key="sk-test",
        base_url="https://api.openai.com/v1/",
        model="whisper-1",
        timeout=5,
    )

    transcript = provider.transcribe("clips/meeting.wav", b"audio-bytes", "en")

    assert captured["url"] == "https://api.openai.com/v1/audio/transcriptions"
    assert captured["data"] == {
        "model": "whisper-1",
        "response_format": "verbose_json",
        "language": "en",
    }
    files = captured["files"]
    assert isinstance(files, dict)
    assert files["file"][0] == "meeting.wav"
    assert files["file"][1] == b"audio-bytes"
    headers = captured["headers"]
    assert isinstance(headers, dict)
    assert headers["Authorization"] == "Bearer sk-test"
    assert transcript.text == "Hello team."
    assert transcript.language == "english"
    assert transcript.duration_seconds == 3.5
    assert [segment.speaker for segment in transcript.segments] == ["unknown", "unknown"]
    assert transcript.segments[0].end == 1.2
    assert transcript.provider == "openai"


def test_openai_transcription_error_hides_the_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    request = httpx.Request("POST", "https://api.openai.com/v1/audio/transcriptions")
    response = httpx.Response(401, request=request, text="invalid key")

    class FakeClient:
        def __init__(self, *args: object, **kwargs: object) -> None:
            del args, kwargs

        def __enter__(self) -> "FakeClient":
            return self

        def __exit__(self, *args: object) -> bool:
            return False

        def post(self, url: str, **kwargs: object) -> httpx.Response:
            del url, kwargs
            return response

    monkeypatch.setattr(httpx, "Client", FakeClient)
    provider = OpenAITranscriptionProvider(
        api_key="sk-test-secret",
        base_url="https://api.openai.com/v1",
        model="whisper-1",
        timeout=5,
    )

    with pytest.raises(ProviderError) as caught:
        provider.transcribe("meeting.wav", b"audio", None)
    message = str(caught.value)
    assert "401" in message
    assert "sk-test-secret" not in message


def test_faster_whisper_reports_a_missing_install(monkeypatch: pytest.MonkeyPatch) -> None:
    import builtins

    real_import = builtins.__import__

    def guarded(name: str, *args: object, **kwargs: object) -> object:
        if name == "faster_whisper":
            raise ImportError("blocked for test")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded)
    with pytest.raises(ProviderConfigError, match="faster-whisper"):
        FasterWhisperTranscriptionProvider(model_size="tiny", device="cpu", compute_type="int8")
