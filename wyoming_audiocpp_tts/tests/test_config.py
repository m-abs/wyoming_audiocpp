"""Tests for TTS Config and VoiceConfig loading and override behavior."""

import pytest

from wyoming_audiocpp_tts.config import (
    Config,
    DEFAULT_AUDIOCPP_URI,
    DEFAULT_ASR_MODEL,
    DEFAULT_VOICE_MODEL,
    VoiceConfig,
)


def test_defaults():
    config = Config()
    assert config.audiocpp_uri == DEFAULT_AUDIOCPP_URI
    assert config.asr_model == DEFAULT_ASR_MODEL
    assert config.tts_voice is None
    assert config.tts_endpoint.endswith("/v1/audio/speech")


def test_tts_endpoint_strips_trailing_slash():
    config = Config(audiocpp_uri="http://localhost:8080/")
    assert config.tts_endpoint == "http://localhost:8080/v1/audio/speech"


def test_voice_request_body_minimal():
    voice = VoiceConfig(model="omnivoice")
    body = voice.request_body("hjælp")
    assert body == {"model": "omnivoice", "input": "hjælp"}


def test_voice_request_body_with_all_fields():
    voice = VoiceConfig(
        model="omnivoice",
        name="female",
        language="da",
        speed=1.5,
        instruct="female",
        extra={"seed": 42},
    )
    body = voice.request_body("hello")
    assert body["model"] == "omnivoice"
    assert body["input"] == "hello"
    assert body["language"] == "da"
    assert body["speed"] == 1.5
    assert body["options"] == {"instruct": "female", "seed": 42}
    assert "voice" not in body


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


def test_voice_from_dict_roundtrip():
    voice = VoiceConfig.from_dict(
        {"model": "omnivoice", "name": "female", "speed": 2.0, "extra": {"seed": 1}}
    )
    assert voice.to_dict() == {
        "model": "omnivoice",
        "name": "female",
        "language": None,
        "speed": 2.0,
        "instruct": None,
        "extra": {"seed": 1},
    }


def test_from_dict_overrides():
    config = Config.from_dict(
        {
            "audiocpp_uri": "http://10.0.0.1:8080",
            "asr_model": "hviske",
            "tts_voice": {"model": "omnivoice", "name": "female"},
        }
    )
    assert config.audiocpp_uri == "http://10.0.0.1:8080"
    assert config.asr_model == "hviske"
    assert config.tts_voice.model == "omnivoice"
    assert config.tts_voice.name == "female"


def test_from_args_loads_config_file():
    import json
    import tempfile

    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as tmp:
        json.dump(
            {
                "audiocpp_uri": "http://example:8080",
                "asr_model": "hviske",
                "tts_voice": {"model": "omnivoice", "name": "female"},
            },
            tmp,
        )
        path = tmp.name

    config = Config.from_args(path)
    assert config.audiocpp_uri == "http://example:8080"
    assert config.asr_model == "hviske"
    assert config.tts_voice.name == "female"


def test_from_args_cli_overrides_config_file():
    import json
    import tempfile

    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as tmp:
        json.dump({"audiocpp_uri": "http://example:8080", "tts_voice": {"model": "omnivoice"}}, tmp)
        path = tmp.name

    config = Config.from_args(
        path,
        asr_model="qwen3_asr",
        voice_overrides={"tts_voice0_name": "male", "tts_voice0_speed": 2.0},
    )
    assert config.asr_model == "qwen3_asr"
    assert config.tts_voice.model == "omnivoice"
    assert config.tts_voice.name == "male"
    assert config.tts_voice.speed == 2.0
    assert config.audiocpp_uri == "http://example:8080"


def test_from_args_partial_override_keeps_file_value():
    import json
    import tempfile

    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as tmp:
        json.dump({"tts_voice": {"model": "omnivoice", "name": "female", "speed": 1.0}}, tmp)
        path = tmp.name

    config = Config.from_args(
        path,
        voice_overrides={"tts_voice0_name": "male"},
    )
    assert config.tts_voice.model == "omnivoice"  # untouched
    assert config.tts_voice.name == "male"  # overridden
    assert config.tts_voice.speed == 1.0  # untouched


def test_from_args_missing_config_uses_defaults():
    config = Config.from_args(
        "/nonexistent/config.json",
        asr_model="hviske",
        voice_overrides={"tts_voice0_model": "omnivoice"},
    )
    assert config.audiocpp_uri == DEFAULT_AUDIOCPP_URI
    assert config.asr_model == "hviske"
    assert config.tts_voice == VoiceConfig(model=DEFAULT_VOICE_MODEL)


def test_extra_merge_preserves_existing():
    voice = VoiceConfig(model="omnivoice", extra={"seed": 1, "keep": True})
    merged = Config._merge_voice(voice, {"extra": {"seed": 2}})
    assert merged.to_dict()["extra"] == {"seed": 2, "keep": True}


def test_validate_rejects_no_voice():
    config = Config(audiocpp_uri="http://localhost:8080", asr_model="hviske")
    with pytest.raises(ValueError, match="No TTS voice configured"):
        config.validate()


def test_validate_rejects_missing_model():
    config = Config(
        audiocpp_uri="http://localhost:8080",
        asr_model="hviske",
        tts_voice=VoiceConfig(model=""),
    )
    with pytest.raises(ValueError, match="tts_voice.model must be set"):
        config.validate()


def test_validate_rejects_bad_scheme():
    config = Config(
        audiocpp_uri="localhost:8080",
        asr_model="hviske",
        tts_voice=VoiceConfig(model="omnivoice"),
    )
    with pytest.raises(ValueError, match="audiocpp_uri scheme"):
        config.validate()


def test_validate_rejects_missing_asr_model():
    config = Config(
        asr_model=None,
        tts_voice=VoiceConfig(model="omnivoice"),
    )
    with pytest.raises(ValueError, match="asr_model must be set"):
        config.validate()
