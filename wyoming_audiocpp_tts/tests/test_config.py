"""Tests for TTS Config and VoiceConfig loading and override behavior."""

import pytest

from wyoming_audiocpp_tts.config import (
    Config,
    DEFAULT_AUDIOCPP_URI,
    DEFAULT_VOICE_MODEL,
    VoiceConfig,
)


def test_defaults():
    config = Config()
    assert config.audiocpp_uri == DEFAULT_AUDIOCPP_URI
    assert len(config.tts_voices) == 1
    assert config.tts_voices[0].model == DEFAULT_VOICE_MODEL
    assert config.tts_endpoint.endswith("/v1/audio/speech")


def test_tts_endpoint_strips_trailing_slash():
    config = Config(audiocpp_uri="http://localhost:8080/")
    assert config.tts_endpoint == "http://localhost:8080/v1/audio/speech"


def test_voice_request_body_minimal():
    voice = VoiceConfig(model="omnivoice")
    body = voice.request_body("hjælp")
    assert body == {"model": "omnivoice", "input": "hjælp"}


def test_voice_request_body_with_options():
    voice = VoiceConfig(
        model="omnivoice",
        name="female",
        language="da",
        speed=1.5,
        options={"instruct": "female voice", "num_inference_steps": "32"},
    )
    body = voice.request_body("hello")
    assert body["model"] == "omnivoice"
    assert body["input"] == "hello"
    assert body["language"] == "da"
    assert body["speed"] == 1.5
    assert body["options"]["instruct"] == "female voice"
    assert body["options"]["num_inference_steps"] == 32.0


def test_voice_request_body_speed_is_number():
    voice = VoiceConfig(model="omnivoice", speed="1.0")
    body = voice.request_body("hi")
    assert body["speed"] == 1.0
    assert isinstance(body["speed"], float)


def test_voice_request_body_omits_unset_optional():
    voice = VoiceConfig(model="omnivoice", name="female")
    body = voice.request_body("hi")
    assert body == {"model": "omnivoice", "input": "hi"}
    assert "options" not in body


def test_voice_name_defaults_to_model():
    voice = VoiceConfig(model="omnivoice")
    assert voice.voice_name == "omnivoice"

    voice2 = VoiceConfig(model="omnivoice", name="female")
    assert voice2.voice_name == "female"


def test_voice_from_dict_roundtrip():
    voice = VoiceConfig.from_dict(
        {"model": "omnivoice", "name": "female", "speed": 2.0, "options": {"seed": 1}}
    )
    assert voice.to_dict() == {
        "model": "omnivoice",
        "name": "female",
        "language": None,
        "speed": 2.0,
        "options": {"seed": 1},
    }


def test_from_dict_overrides():
    config = Config.from_dict(
        {
            "audiocpp_uri": "http://10.0.0.1:8080",
            "tts_voices": [
                {"model": "omnivoice", "name": "female"},
                {"model": "omnivoice", "name": "male"},
            ],
        }
    )
    assert config.audiocpp_uri == "http://10.0.0.1:8080"
    assert len(config.tts_voices) == 2
    assert config.tts_voices[0].model == "omnivoice"
    assert config.tts_voices[0].name == "female"
    assert config.tts_voices[1].name == "male"


def test_from_args_loads_config_file():
    import json
    import tempfile

    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as tmp:
        json.dump(
            {
                "audiocpp_uri": "http://example:8080",
                "tts_voices": [
                    {"model": "omnivoice", "name": "female"},
                    {"model": "omnivoice", "name": "male"},
                ],
            },
            tmp,
        )
        path = tmp.name

    config = Config.from_args(path)
    assert config.audiocpp_uri == "http://example:8080"
    assert len(config.tts_voices) == 2
    assert config.tts_voices[0].name == "female"


def test_from_args_missing_config_uses_defaults():
    config = Config.from_args("/nonexistent/config.json")
    assert config.audiocpp_uri == DEFAULT_AUDIOCPP_URI
    assert len(config.tts_voices) == 1
    assert config.tts_voices[0].model == DEFAULT_VOICE_MODEL


def test_validate_rejects_empty_voices():
    config = Config(audiocpp_uri="http://localhost:8080", tts_voices=[])
    with pytest.raises(ValueError, match="No TTS voices configured"):
        config.validate()


def test_validate_rejects_missing_model():
    config = Config(
        audiocpp_uri="http://localhost:8080",
        tts_voices=[VoiceConfig(model="")],
    )
    with pytest.raises(ValueError, match="tts_voices\\[\\].model must be set"):
        config.validate()


def test_validate_rejects_bad_scheme():
    config = Config(
        audiocpp_uri="localhost:8080",
        tts_voices=[VoiceConfig(model="omnivoice")],
    )
    with pytest.raises(ValueError, match="audiocpp_uri scheme"):
        config.validate()


def test_validate_rejects_bad_web_server_port():
    config = Config(
        audiocpp_uri="http://localhost:8080",
        tts_voices=[VoiceConfig(model="omnivoice")],
        tts_web_server=True,
        tts_web_server_port=0,
    )
    with pytest.raises(ValueError, match="tts_web_server_port"):
        config.validate()
