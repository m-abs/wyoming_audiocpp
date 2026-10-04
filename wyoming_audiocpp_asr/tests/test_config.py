"""Tests for Config loading and merging."""

import pytest

from wyoming_audiocpp_asr.config import (
    Config,
    DEFAULT_AUDIOCPP_URI,
    DEFAULT_LANGUAGE,
    DEFAULT_MODEL,
    DEFAULT_URI,
    DEFAULT_WEB_SERVER_HOST,
    DEFAULT_WEB_SERVER_PORT,
)


def test_defaults():
    config = Config()
    assert config.audiocpp_uri == DEFAULT_AUDIOCPP_URI
    assert config.asr_model == DEFAULT_MODEL
    assert config.asr_language == DEFAULT_LANGUAGE
    assert config.transcription_endpoint.endswith("/v1/audio/transcriptions")


def test_transcription_endpoint_strips_trailing_slash():
    config = Config(audiocpp_uri="http://localhost:8080/")
    assert config.transcription_endpoint == "http://localhost:8080/v1/audio/transcriptions"


def test_from_dict_overrides():
    config = Config.from_dict(
        {"audiocpp_uri": "http://10.0.0.1:8080", "asr_model": "hviske", "asr_language": "en"}
    )
    assert config.audiocpp_uri == "http://10.0.0.1:8080"
    assert config.asr_model == "hviske"
    assert config.asr_language == "en"


def test_from_args_loads_config_file():
    import tempfile
    import json

    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as tmp:
        json.dump({"audiocpp_uri": "http://example:8080", "asr_model": "hviske"}, tmp)
        path = tmp.name

    config = Config.from_args(path)
    assert config.audiocpp_uri == "http://example:8080"
    assert config.asr_model == "hviske"


def test_from_args_cli_overrides_config_file():
    import tempfile
    import json

    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as tmp:
        json.dump({"audiocpp_uri": "http://example:8080", "asr_model": "hviske"}, tmp)
        path = tmp.name

    config = Config.from_args(path, asr_model="qwen3_asr", asr_language="da")
    assert config.asr_model == "qwen3_asr"
    assert config.asr_language == "da"
    assert config.audiocpp_uri == "http://example:8080"


def test_from_args_missing_config_uses_defaults():
    config = Config.from_args("/nonexistent/config.json", asr_model="hviske")
    assert config.audiocpp_uri == DEFAULT_AUDIOCPP_URI
    assert config.asr_model == "hviske"


def test_validate_rejects_bad_scheme():
    config = Config(audiocpp_uri="localhost:8080", asr_model="hviske")
    with pytest.raises(ValueError):
        config.validate()


def test_validate_rejects_empty_model():
    config = Config(audiocpp_uri="http://localhost:8080", asr_model="")
    with pytest.raises(ValueError):
        config.validate()


def test_new_defaults():
    config = Config()
    assert config.asr_uri == DEFAULT_URI
    assert config.enable_zeroconf is False
    assert config.asr_web_server is False
    assert config.asr_web_server_host == DEFAULT_WEB_SERVER_HOST
    assert config.asr_web_server_port == DEFAULT_WEB_SERVER_PORT
    assert config.asr_web_server_allow is None


def test_parse_tcp_uri():
    assert Config(asr_uri="tcp://10.0.0.1:11301").parse_tcp_uri() == ("10.0.0.1", 11301)
    with pytest.raises(ValueError):
        Config(asr_uri="tcp://0.0.0.0").parse_tcp_uri()
    with pytest.raises(ValueError):
        Config(asr_uri="unix:///tmp/wyoming").parse_tcp_uri()


def test_validate_rejects_non_tcp_uri():
    config = Config(asr_uri="stdio://", asr_model="hviske")
    with pytest.raises(ValueError):
        config.validate()

def test_validate_accepts_language_list():
    config = Config(audiocpp_uri="http://localhost:8080", asr_model="hviske", asr_language=["da", "en"])
    config.validate()


def test_validate_rejects_non_string_language_list_item():
    config = Config(audiocpp_uri="http://localhost:8080", asr_model="hviske", asr_language=["da", 42])
    with pytest.raises(ValueError):
        config.validate()


def test_validate_rejects_non_string_language():
    config = Config(audiocpp_uri="http://localhost:8080", asr_model="hviske", asr_language=42)
    with pytest.raises(ValueError):
        config.validate()


def test_validate_rejects_bad_web_server_port():
    config = Config(asr_model="hviske", asr_web_server=True, asr_web_server_port=0)
    with pytest.raises(ValueError):
        config.validate()


def test_from_dict_new_fields():
    config = Config.from_dict(
        {
            "asr_uri": "tcp://10.0.0.1:55002",
            "enable_zeroconf": True,
            "asr_web_server": True,
            "asr_web_server_host": "0.0.0.0",
            "asr_web_server_port": 5001,
            "asr_web_server_allow": ["10.0.0.0/8"],
        }
    )
    assert config.asr_uri == "tcp://10.0.0.1:55002"
    assert config.enable_zeroconf is True
    assert config.asr_web_server is True
    assert config.asr_web_server_host == "0.0.0.0"
    assert config.asr_web_server_port == 5001
    assert config.asr_web_server_allow == ["10.0.0.0/8"]


def test_from_args_cli_overrides_new_fields():
    config = Config.from_args(
        None, asr_uri="tcp://127.0.0.1:55009", enable_zeroconf=True, asr_web_server=True
    )
    assert config.asr_uri == "tcp://127.0.0.1:55009"
    assert config.enable_zeroconf is True
    assert config.asr_web_server is True


def test_from_args_env_var_applied(monkeypatch):
    monkeypatch.setenv("WYO_ASR_URI", "tcp://127.0.0.1:55007")
    monkeypatch.setenv("WYO_ENABLE_ZEROCONF", "true")
    monkeypatch.setenv("WYO_ASR_WEB_SERVER_PORT", "5002")
    monkeypatch.setenv("WYO_ASR_WEB_SERVER_ALLOW", "10.0.0.1,192.168.1.0/24")
    config = Config.from_args(None)
    assert config.asr_uri == "tcp://127.0.0.1:55007"
    assert config.enable_zeroconf is True
    assert config.asr_web_server_port == 5002
    assert config.asr_web_server_allow == ["10.0.0.1", "192.168.1.0/24"]


def test_from_args_cli_beats_env(monkeypatch):
    monkeypatch.setenv("WYO_ASR_URI", "tcp://127.0.0.1:55007")
    config = Config.from_args(None, asr_uri="tcp://127.0.0.1:55009")
    assert config.asr_uri == "tcp://127.0.0.1:55009"
