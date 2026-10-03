"""Tests for the TTS client request/response contract."""

from unittest import mock

import pytest

from wyoming_audiocpp_tts import audiocpp_client
from wyoming_audiocpp_tts.config import VoiceConfig


def make_response(payload: bytes):
    response = mock.Mock()
    response.status_code = 200
    response.content = payload
    return response


def test_text_to_speech_minimal():
    voice = VoiceConfig(model="omnivoice")
    captured = {}

    def fake_post(url, json=None, timeout=None, **kwargs):
        captured["url"] = url
        captured["json"] = json
        captured["timeout"] = timeout
        return make_response(b"RIFF....WAVE")

    with mock.patch.object(audiocpp_client.requests, "post", side_effect=fake_post):
        audio = audiocpp_client.text_to_speech(
            "http://localhost:8080/v1/audio/speech", voice, text="hello"
        )

    assert audio == b"RIFF....WAVE"
    assert captured["url"].endswith("/v1/audio/speech")
    assert captured["json"] == {"model": "omnivoice", "input": "hello"}
    assert captured["timeout"] == 120.0


def test_text_to_speech_full_body():
    voice = VoiceConfig(
        model="omnivoice",
        name="female",
        language="da",
        speed=1.5,
        options={"instruct": "female voice", "num_inference_steps": "32"},
    )
    captured = {}

    def fake_post(url, json=None, timeout=None, **kwargs):
        captured["json"] = json
        return make_response(b"RIP")

    with mock.patch.object(audiocpp_client.requests, "post", side_effect=fake_post):
        audiocpp_client.text_to_speech(
            "http://localhost:8080/v1/audio/speech", voice, text="hi"
        )

    assert captured["json"] == {
        "model": "omnivoice",
        "input": "hi",
        "language": "da",
        "speed": 1.5,
        "options": {"instruct": "female voice", "num_inference_steps": 32.0},
    }


def test_text_to_speech_http_error_propagates():
    def boom(url, **kwargs):
        raise RuntimeError("audio.cpp exploded")

    with mock.patch.object(audiocpp_client.requests, "post", side_effect=boom):
        with pytest.raises(RuntimeError, match="audio.cpp exploded"):
            audiocpp_client.text_to_speech(
                "http://localhost:8080/v1/audio/speech",
                VoiceConfig(model="omnivoice"),
                text="hi",
            )
