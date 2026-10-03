"""Tests for the TTS HTTP bridge endpoints using a real Flask app."""

from unittest import mock

import pytest

from wyoming_audiocpp_tts import audiocpp_client
from wyoming_audiocpp_tts.config import Config, VoiceConfig
from wyoming_audiocpp_tts.tts_server import create_app

MODEL = "omnivoice"
NAME = "female"
LANGUAGE = "da"


def build_client(config: Config):
    return create_app(config).test_client()


def post_text(client, body, **params):
    response = client.post("/api/tts", json=body, query_string=params)
    return response


def _config(voices=None):
    if voices is None:
        return Config.from_args(None)
    return Config(tts_voices=voices)


def test_success_passes_args_and_shapes_response():
    config = _config([VoiceConfig(model=MODEL, name=NAME, language=LANGUAGE)])
    client = build_client(config)

    captured = {}

    def fake_post(url, json=None, timeout=None, **kwargs):
        captured["url"] = url
        captured["json"] = json
        captured["timeout"] = timeout
        response = mock.Mock()
        response.status_code = 200
        response.content = b"RIFF....WAVE"
        return response

    with mock.patch.object(audiocpp_client.requests, "post", side_effect=fake_post):
        response = post_text(client, {"text": "hjalp"})

    assert response.status_code == 200
    assert response.data == b"RIFF....WAVE"
    assert response.mimetype == "audio/wav"

    assert captured["url"].endswith("/v1/audio/speech")
    assert captured["json"] == {
        "model": MODEL,
        "input": "hjalp",
        "language": LANGUAGE,
    }
    assert captured["timeout"] == 120.0


def test_success_forwards_options():
    config = _config([VoiceConfig(model=MODEL, options={"seed": 7})])
    client = build_client(config)

    captured = {}

    def fake_post(url, json=None, timeout=None, **kwargs):
        captured["json"] = json
        return mock.Mock(status_code=200, content=b"R")

    with mock.patch.object(audiocpp_client.requests, "post", side_effect=fake_post):
        post_text(client, {"text": "hi"})

    assert captured["json"] == {"model": MODEL, "input": "hi", "options": {"seed": 7}}


def test_model_defaults_to_config():
    config = _config([VoiceConfig(model=MODEL)])
    client = build_client(config)

    captured = {}

    def fake_post(url, json=None, timeout=None, **kwargs):
        captured["json"] = json
        return mock.Mock(status_code=200, content=b"R")

    with mock.patch.object(audiocpp_client.requests, "post", side_effect=fake_post):
        post_text(client, {"text": "hi"})

    assert captured["json"] == {"model": MODEL, "input": "hi"}
    assert "voice" not in captured["json"]
    assert "language" not in captured["json"]


def test_empty_request_rejected():
    config = _config([VoiceConfig(model=MODEL)])
    client = build_client(config)
    response = post_text(client, {})
    assert response.status_code == 400


def test_missing_text_rejected():
    config = _config([VoiceConfig(model=MODEL)])
    client = build_client(config)
    response = post_text(client, {})
    assert response.status_code == 400


def test_audiocpp_error_returns_502():
    config = _config([VoiceConfig(model=MODEL)])
    client = build_client(config)

    def boom(url, **kwargs):
        raise RuntimeError("audio.cpp exploded")

    with mock.patch.object(audiocpp_client.requests, "post", side_effect=boom):
        response = post_text(client, {"text": "hi"})

    assert response.status_code == 502
    assert "audio.cpp exploded" in response.get_data(as_text=True)


def test_index_reports_voices():
    config = _config([VoiceConfig(model=MODEL, name=NAME)])
    client = build_client(config)
    response = client.get("/")
    body = response.get_json()
    assert body["name"] == "wyoming_audiocpp_tts"
    assert body["tts_voices"] == [NAME]


def test_api_voices_endpoint():
    config = _config([VoiceConfig(model=MODEL, name="female"), VoiceConfig(model=MODEL, name="male")])
    client = build_client(config)
    response = client.get("/api/voices")
    body = response.get_json()
    assert body["voices"] == [
        {"name": "female", "model": MODEL},
        {"name": "male", "model": MODEL},
    ]
