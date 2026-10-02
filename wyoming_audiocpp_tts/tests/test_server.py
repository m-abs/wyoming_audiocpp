"""Tests for the TTS HTTP bridge endpoints using a real Flask app."""

from unittest import mock

import pytest

from wyoming_audiocpp_tts import audiocpp_client
from wyoming_audiocpp_tts.config import Config
from wyoming_audiocpp_tts.tts_server import create_app

MODEL = "omnivoice"
NAME = "female"
LANGUAGE = "da"


def build_client(config: Config):
    return create_app(config).test_client()


def post_text(client, body, **params):
    response = client.post("/api/tts", json=body, query_string=params)
    return response


def test_success_passes_args_and_shapes_response():
    config = Config.from_args(None, asr_model="hviske", voice_overrides={
        "tts_voice0_model": MODEL,
        "tts_voice0_name": NAME,
        "tts_voice0_language": LANGUAGE,
    })
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


def test_success_forwards_extra():
    config = Config.from_args(None, voice_overrides={"tts_voice0_model": MODEL, "tts_voice0_extra": {"seed": 7}})
    client = build_client(config)

    captured = {}

    def fake_post(url, json=None, timeout=None, **kwargs):
        captured["json"] = json
        return mock.Mock(status_code=200, content=b"R")

    with mock.patch.object(audiocpp_client.requests, "post", side_effect=fake_post):
        post_text(client, {"text": "hi"})

    assert captured["json"] == {"model": MODEL, "input": "hi", "options": {"seed": 7}}


def test_model_defaults_to_config():
    config = Config.from_args(None, voice_overrides={"tts_voice0_model": MODEL})
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
    config = Config.from_args(None, voice_overrides={"tts_voice0_model": MODEL})
    client = build_client(config)
    response = post_text(client, {})
    assert response.status_code == 400


def test_missing_text_rejected():
    config = Config.from_args(None, voice_overrides={"tts_voice0_model": MODEL})
    client = build_client(config)
    response = post_text(client, {})
    assert response.status_code == 400


def test_audiocpp_error_returns_502():
    config = Config.from_args(None, voice_overrides={"tts_voice0_model": MODEL})
    client = build_client(config)

    def boom(url, **kwargs):
        raise RuntimeError("audio.cpp exploded")

    with mock.patch.object(audiocpp_client.requests, "post", side_effect=boom):
        response = post_text(client, {"text": "hi"})

    assert response.status_code == 502
    assert "audio.cpp exploded" in response.get_data(as_text=True)


def test_index_reports_voice():
    config = Config.from_args(None, voice_overrides={
        "tts_voice0_model": MODEL,
        "tts_voice0_name": NAME,
    })
    client = build_client(config)
    response = client.get("/")
    body = response.get_json()
    assert body["name"] == "wyoming_audiocpp_tts"
    assert body["tts_model"] == MODEL
    assert body["tts_name"] == NAME
    assert body["asr_model"] == "hviske"
