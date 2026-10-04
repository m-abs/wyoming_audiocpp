"""Tests for the ASR HTTP bridge endpoints using a real Flask app."""

from unittest import mock

import pytest
from wyoming_audiocpp_asr import audiocpp_client
from wyoming_audiocpp_asr.asr_server import create_app
from wyoming_audiocpp_asr.config import AsrConfig

from . import synth_wav

MODEL = "hviske"
LANGUAGE = "da"


def build_client(config: AsrConfig):
    return create_app(config).test_client()


def post_wav(client, body, **params):
    response = client.post(
        "/api/speech-to-text",
        data=body,
        content_type="audio/wav",
        query_string=params,
    )
    return response


def test_success_passes_args_and_shapes_response():
    config = AsrConfig.from_args(None, asr_model=MODEL, asr_language=LANGUAGE)
    client = build_client(config)

    captured = {}

    def fake_post(url, data=None, files=None, timeout=None, **kwargs):
        captured["url"] = url
        captured["data"] = dict(data or {})
        captured["files"] = dict(files or {})
        captured["timeout"] = timeout
        response = mock.Mock()
        response.status_code = 200
        response.json.return_value = {"text": "hallo verden", "language": "da"}
        return response

    with mock.patch.object(audiocpp_client.requests, "post", side_effect=fake_post):
        response = post_wav(client, synth_wav.make_wav(), model=MODEL, language=LANGUAGE)

    assert response.status_code == 200
    body = response.get_json()
    assert body == {"text": "hallo verden", "language": "da"}

    assert captured["url"].endswith("/v1/audio/transcriptions")
    assert captured["data"] == {"model": MODEL, "language": LANGUAGE}
    assert "file" in captured["files"]
    assert captured["timeout"] == 120.0


def test_model_defaults_to_config():
    config = AsrConfig.from_args(None, asr_model=MODEL)
    client = build_client(config)

    captured = {}

    def fake_post(url, data=None, files=None, timeout=None, **kwargs):
        captured["data"] = dict(data or {})
        response = mock.Mock()
        response.status_code = 200
        response.json.return_value = {"text": "", "language": None}
        return response

    with mock.patch.object(audiocpp_client.requests, "post", side_effect=fake_post):
        post_wav(client, synth_wav.make_wav())

    assert captured["data"]["model"] == MODEL
    assert "language" not in captured["data"]


def test_language_query_overrides_config():
    config = AsrConfig.from_args(None, asr_model=MODEL, asr_language=LANGUAGE)
    client = build_client(config)

    captured = {}

    def fake_post(url, data=None, files=None, timeout=None, **kwargs):
        captured["data"] = dict(data or {})
        response = mock.Mock()
        response.status_code = 200
        response.json.return_value = {"text": "", "language": None}
        return response

    with mock.patch.object(audiocpp_client.requests, "post", side_effect=fake_post):
        post_wav(client, synth_wav.make_wav(), model=MODEL, language="en")

    assert captured["data"]["language"] == "en"


def test_empty_request_rejected():
    config = AsrConfig.from_args(None, asr_model=MODEL)
    client = build_client(config)
    response = client.post("/api/speech-to-text", content_type="audio/wav")
    assert response.status_code == 400


def test_audiocpp_error_returns_502():
    config = AsrConfig.from_args(None, asr_model=MODEL)
    client = build_client(config)

    def boom(*args, **kwargs):
        raise RuntimeError("audio.cpp exploded")

    with mock.patch.object(audiocpp_client.requests, "post", side_effect=boom):
        response = post_wav(client, synth_wav.make_wav())

    assert response.status_code == 502
    assert "audio.cpp exploded" in response.get_data(as_text=True)


def test_info_requires_models():
    config = AsrConfig.from_args(None, asr_model=MODEL)
    client = build_client(config)

    response = client.get("/api/info")
    assert response.status_code == 200
