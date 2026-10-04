"""Tests for the demo web server (the --web-server add-on)."""

from __future__ import annotations

import io
import pytest

from wyoming_audiocpp_asr import audiocpp_client
from wyoming_audiocpp_asr.config import AsrConfig
from wyoming_audiocpp_asr.web_server import make_asr_web_server

MODEL = "hviske"

from . import synth_wav  # noqa: E402


@pytest.fixture
def client():
    config = AsrConfig.from_args(None, asr_model=MODEL)
    return make_asr_web_server(config).test_client()


def test_index_get(client):
    response = client.get("/")
    assert response.status_code == 200
    assert response.content_type.startswith("text/html")
    html = response.get_data(as_text=True)
    assert "Transcribe" in html
    assert "/api/speech-to-text" in html


def test_health_get(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json == {"status": "ok"}


def test_status_get(client):
    response = client.get("/api/status")
    assert response.status_code == 200
    body = response.json
    assert body["service"] == "wyoming-audiocpp-asr"
    assert body["model"] == MODEL


def test_info_still_served(client):
    """The /api/info endpoint of the HTTP bridge stays available."""
    response = client.get("/api/info")
    assert response.status_code == 200
    assert "asr" in response.json


def test_transcribe_post(client, monkeypatch):
    wav = synth_wav.make_wav()
    monkeypatch.setattr(
        audiocpp_client,
        "transcribe",
        lambda *args, **kwargs: {"text": "hej verden", "language": "da"},
    )
    response = client.post(
        "/api/speech-to-text",
        data={"file": (io.BytesIO(wav), "audio.wav")},
    )
    assert response.status_code == 200
    assert response.json["text"] == "hej verden"
    assert response.json["language"] == "da"


def test_transcribe_post_language_param(client, monkeypatch):
    wav = synth_wav.make_wav()
    captured = {}

    def fake(endpoint, wav_bytes, model, language, *, timeout=120.0):
        captured["language"] = language
        return {"text": "hi", "language": "en"}

    monkeypatch.setattr(audiocpp_client, "transcribe", fake)
    response = client.post(
        "/api/speech-to-text?language=en",
        data={"file": (io.BytesIO(wav), "audio.wav")},
    )
    assert response.status_code == 200
    assert response.json["language"] == "en"
    assert captured["language"] == "en"


def test_transcribe_post_empty_rejected(client):
    response = client.post("/api/speech-to-text")
    assert response.status_code == 400


def test_transcribe_post_upstream_error_returns_502(client, monkeypatch):
    monkeypatch.setattr(
        audiocpp_client,
        "transcribe",
        lambda *args, **kwargs: (_ for _ in ()).throw(ConnectionError("boom")),
    )
    response = client.post(
        "/api/speech-to-text",
        data={"file": (io.BytesIO(synth_wav.make_wav()), "audio.wav")},
    )
    assert response.status_code == 502
