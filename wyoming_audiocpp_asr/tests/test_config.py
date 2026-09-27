"""Tests for Config loading and merging."""

import pytest

from wyoming_audiocpp_asr.config import (
    Config,
    DEFAULT_AUDIOCPP_URI,
    DEFAULT_LANGUAGE,
    DEFAULT_MODEL,
)


def test_defaults():
    config = Config()
    assert config.audiocpp_uri == DEFAULT_AUDIOCPP_URI
    assert config.model == DEFAULT_MODEL
    assert config.language == DEFAULT_LANGUAGE
    assert config.transcription_endpoint.endswith("/v1/audio/transcriptions")


def test_transcription_endpoint_strips_trailing_slash():
    config = Config(audiocpp_uri="http://localhost:8080/")
    assert config.transcription_endpoint == "http://localhost:8080/v1/audio/transcriptions"


def test_from_dict_overrides():
    config = Config.from_dict(
        {"audiocpp_uri": "http://10.0.0.1:8080", "model": "hviske", "language": "en"}
    )
    assert config.audiocpp_uri == "http://10.0.0.1:8080"
    assert config.model == "hviske"
    assert config.language == "en"


def test_from_args_loads_config_file():
    import tempfile
    import json

    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as tmp:
        json.dump({"audiocpp_uri": "http://example:8080", "model": "hviske"}, tmp)
        path = tmp.name

    config = Config.from_args(path)
    assert config.audiocpp_uri == "http://example:8080"
    assert config.model == "hviske"


def test_from_args_cli_overrides_config_file():
    import tempfile
    import json

    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as tmp:
        json.dump({"audiocpp_uri": "http://example:8080", "model": "hviske"}, tmp)
        path = tmp.name

    config = Config.from_args(path, model="qwen3_asr", language="da")
    assert config.model == "qwen3_asr"
    assert config.language == "da"
    assert config.audiocpp_uri == "http://example:8080"


def test_from_args_missing_config_uses_defaults():
    config = Config.from_args("/nonexistent/config.json", model="hviske")
    assert config.audiocpp_uri == DEFAULT_AUDIOCPP_URI
    assert config.model == "hviske"


def test_validate_rejects_bad_scheme():
    config = Config(audiocpp_uri="localhost:8080", model="hviske")
    with pytest.raises(ValueError):
        config.validate()


def test_validate_rejects_empty_model():
    config = Config(audiocpp_uri="http://localhost:8080", model="")
    with pytest.raises(ValueError):
        config.validate()
