"""HTTP API coverage with the fake transcription provider."""

from pathlib import Path

from fastapi.testclient import TestClient

from app.main import create_app
from app.services.errors import ProviderConfigError, ProviderError
from app.services.speakers import SEGMENT_SECONDS
from tests.conftest import build_settings, wav_bytes

DIALPLAN = "20261102-143015-1730554215.23-1001-200.wav"
SUMMARY = (
    "Recorded call from 1001 to 200. I am calling about invoice 1842. Invoice 1842 is still unpaid."
)


def test_root_health_and_ui(client: TestClient) -> None:
    root = client.get("/")
    health = client.get("/health")
    ui = client.get("/ui")

    assert root.status_code == 200
    body = root.json()
    assert body["status"] == "ok"
    assert body["transcription_provider"] == "fake"
    assert body["watcher"] == "disabled"
    assert body["calls"] == 0
    assert body["docs"] == "/docs"
    assert body["ui"] == "/ui"
    assert health.status_code == 200
    assert health.json()["transcription_provider"] == "fake"
    assert ui.status_code == 200
    assert "Call recorder" in ui.text
    assert "Search transcripts" in ui.text
    assert "textContent" in ui.text


def test_upload_parses_the_dialplan_filename_and_returns_speakers(client: TestClient) -> None:
    response = client.post(
        "/calls",
        files={"file": (DIALPLAN, wav_bytes(), "audio/wav")},
        data={"language": "en"},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["caller"] == "1001"
    assert body["callee"] == "200"
    assert body["uniqueid"] == "1730554215.23"
    assert body["started_at"] == "2026-11-02T14:30:15"
    assert body["provider"] == "fake"
    assert body["source"] == "upload"
    assert body["playable"] is True
    assert body["summary"] == SUMMARY
    assert body["duration_seconds"] == 4 * SEGMENT_SECONDS
    assert [segment["speaker"] for segment in body["segments"]] == [
        "caller",
        "callee",
        "caller",
        "callee",
    ]
    assert "invoice 1842" in body["segments"][0]["text"]
    assert "does not decode audio" in body["notice"]
    assert body["audio_url"] == f"/calls/{body['id']}/audio"

    audio = client.get(body["audio_url"])
    assert audio.status_code == 200
    assert audio.headers["content-type"].startswith("audio/wav")
    assert audio.content == wav_bytes()
    assert "inline" in audio.headers["content-disposition"]

    transcript = client.get(f"/calls/{body['id']}/transcript")
    assert transcript.status_code == 200
    assert transcript.json()["summary"] == SUMMARY
    assert "ticket 5521" in transcript.json()["text"]


def test_explicit_fields_override_the_filename(client: TestClient) -> None:
    response = client.post(
        "/calls",
        files={"file": (DIALPLAN, wav_bytes(), "audio/wav")},
        data={"caller": "9999", "direction": "out", "started_at": "2026-11-02T16:00:00"},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["caller"] == "9999"
    assert body["callee"] == "200"
    assert body["direction"] == "outbound"
    assert body["started_at"] == "2026-11-02T16:00:00"


def test_text_transcript_keeps_speaker_lines(client: TestClient) -> None:
    transcript = "agent: The queue is clear.\ncustomer: Thanks, I will call back.\n"
    response = client.post(
        "/calls",
        files={"file": ("notes.txt", transcript.encode(), "text/plain")},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["playable"] is False
    assert [segment["speaker"] for segment in body["segments"]] == ["callee", "caller"]
    assert "text file" in body["notice"]
    assert "queue is clear" in body["segments"][0]["text"]


def test_cdr_join_and_search(tmp_path: Path) -> None:
    cdr_path = tmp_path / "Master.csv"
    settings = build_settings(tmp_path, cdr_path=str(cdr_path))
    app = create_app(settings)
    with TestClient(app) as client:
        uploaded = client.post(
            "/cdr",
            files={
                "file": (
                    "Master.csv",
                    b"uniqueid,src,dst,dcontext,clid,disposition,billsec,start\n"
                    b"1730554215.23,1001,200,from-internal,Ada Obi <1001>,ANSWERED,142,"
                    b"2026-11-02 14:30:15\n",
                    "text/csv",
                )
            },
        )
        assert uploaded.status_code == 200
        assert uploaded.json() == {"rows": 1}

        created = client.post(
            "/calls",
            files={"file": ("1730554215.23.wav", wav_bytes(), "audio/wav")},
        )
        assert created.status_code == 201
        body = created.json()
        assert body["caller"] == "1001"
        assert body["callee"] == "200"
        assert body["caller_name"] == "Ada Obi"
        assert body["direction"] == "internal"
        assert body["disposition"] == "ANSWERED"
        assert body["duration_seconds"] == 142
        assert body["summary"].startswith("Answered call from 1001 to 200 (internal).")

        found = client.get("/search", params={"q": "INVOICE"})
        assert found.status_code == 200
        results = found.json()["results"]
        assert len(results) == 1
        assert "invoice 1842" in results[0]["snippet"].lower()

        by_party = client.get("/search", params={"q": "Ada"})
        assert by_party.json()["results"][0]["id"] == body["id"]

        missing = client.get("/search", params={"q": "no-such-phrase"})
        assert missing.json()["results"] == []

        wildcard = client.get("/search", params={"q": "%"})
        assert wildcard.json()["results"] == []

        listed = client.get("/calls", params={"uniqueid": "1730554215.23"})
        assert listed.json()["total"] == 1
        assert client.get("/calls", params={"direction": "outbound"}).json()["total"] == 0


def test_list_pagination_is_newest_first(client: TestClient) -> None:
    later = "20261102-150000-1730559999.2-1001-200.wav"
    earlier = "20261102-140000-1730551111.2-1001-201.wav"
    for name in (earlier, later):
        response = client.post("/calls", files={"file": (name, wav_bytes(), "audio/wav")})
        assert response.status_code == 201

    page = client.get("/calls", params={"limit": 1, "offset": 1})
    assert page.status_code == 200
    body = page.json()
    assert body["total"] == 2
    assert body["calls"][0]["callee"] == "201"
    assert body["calls"][0]["started_at"] == "2026-11-02T14:00:00"


def test_delete_removes_the_audio(client: TestClient, settings) -> None:
    created = client.post("/calls", files={"file": (DIALPLAN, wav_bytes(), "audio/wav")})
    call_id = created.json()["id"]
    recordings = Path(settings.recordings_dir)
    assert list(recordings.glob("*"))

    deleted = client.delete(f"/calls/{call_id}")
    assert deleted.status_code == 204
    assert client.get(f"/calls/{call_id}").status_code == 404
    assert client.get(f"/calls/{call_id}/audio").status_code == 404
    assert list(recordings.glob("*")) == []


def test_rejects_empty_oversize_and_unknown_types(tmp_path) -> None:
    app = create_app(build_settings(tmp_path, max_upload_bytes=8))
    with TestClient(app) as client:
        empty = client.post("/calls", files={"file": ("a.wav", b"", "audio/wav")})
        assert empty.status_code == 400
        assert empty.json()["detail"] == "Upload is empty."

        over = client.post("/calls", files={"file": ("a.wav", b"123456789", "audio/wav")})
        assert over.status_code == 413

        bad = client.post("/calls", files={"file": ("a.exe", b"1234", "application/octet-stream")})
        assert bad.status_code == 415


def test_bad_timestamp_and_language_are_rejected(client: TestClient) -> None:
    bad_time = client.post(
        "/calls",
        files={"file": (DIALPLAN, wav_bytes(), "audio/wav")},
        data={"started_at": "tomorrow"},
    )
    assert bad_time.status_code == 400

    bad_language = client.post(
        "/calls",
        files={"file": (DIALPLAN, wav_bytes(), "audio/wav")},
        data={"language": "this-is-way-too-long"},
    )
    assert bad_language.status_code == 400


def test_missing_call_is_404(client: TestClient) -> None:
    assert client.get("/calls/does-not-exist").status_code == 404
    assert client.get("/calls/does-not-exist").json()["detail"] == "Call not found."


def test_hostile_filename_cannot_escape_the_recordings_dir(client: TestClient, settings) -> None:
    response = client.post(
        "/calls",
        files={"file": ("../../etc/passwd.wav", wav_bytes(), "audio/wav")},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["filename"] == "passwd.wav"
    recordings = Path(settings.recordings_dir).resolve()
    stored = list(recordings.glob("*"))
    assert len(stored) == 1
    assert stored[0].parent == recordings


def test_provider_failures_do_not_store_a_call(client: TestClient) -> None:
    class Broken:
        name = "broken"

        def transcribe(self, filename: str, data: bytes, language: str | None) -> None:
            del filename, data, language
            raise ProviderError("upstream down")

    client.app.state.archive.provider = Broken()
    response = client.post("/calls", files={"file": (DIALPLAN, wav_bytes(), "audio/wav")})
    assert response.status_code == 502
    assert response.json()["detail"] == "upstream down"
    assert client.get("/calls").json()["total"] == 0

    class Missing:
        name = "missing"

        def transcribe(self, filename: str, data: bytes, language: str | None) -> None:
            del filename, data, language
            raise ProviderConfigError("provider is not configured")

    client.app.state.archive.provider = Missing()
    denied = client.post("/calls", files={"file": (DIALPLAN, wav_bytes(), "audio/wav")})
    assert denied.status_code == 503


def test_cdr_endpoint_requires_a_path(client: TestClient) -> None:
    response = client.post("/cdr", files={"file": ("Master.csv", b"uniqueid,src\n", "text/csv")})
    assert response.status_code == 400
    assert "CDR_PATH" in response.json()["detail"]


def test_watcher_thread_starts_when_enabled(tmp_path) -> None:
    monitor = tmp_path / "spool"
    monitor.mkdir()
    app = create_app(
        build_settings(
            tmp_path,
            watch_enabled=True,
            monitor_dir=str(monitor),
            watch_interval_seconds=30,
        )
    )
    with TestClient(app) as client:
        body = client.get("/health").json()
        assert body["watcher"] == "running"
    assert app.state.watcher.running is False
