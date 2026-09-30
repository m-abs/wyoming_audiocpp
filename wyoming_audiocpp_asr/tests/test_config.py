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


def test_new_defaults():
    config = Config()
    assert config.uri == DEFAULT_URI
    assert config.enable_zeroconf is False
    assert config.zeroconf_name is None
    assert config.web_server is False
    assert config.web_server_host == DEFAULT_WEB_SERVER_HOST
    assert config.web_server_port == DEFAULT_WEB_SERVER_PORT
    assert config.web_server_allow is None


def test_parse_tcp_uri():
    assert Config(uri="tcp://10.0.0.1:55001").parse_tcp_uri() == ("10.0.0.1", 55001)
    with pytest.raises(ValueError):
        Config(uri="tcp://0.0.0.0").parse_tcp_uri()
    with pytest.raises(ValueError):
        Config(uri="unix:///tmp/wyoming").parse_tcp_uri()


def test_validate_rejects_non_tcp_uri():
    config = Config(uri="stdio://", model="hviske")
    with pytest.raises(ValueError):
        config.validate()


def test_validate_rejects_bad_web_server_port():
    config = Config(model="hviske", web_server=True, web_server_port=0)
    with pytest.raises(ValueError):
        config.validate()


def test_from_dict_new_fields():
    config = Config.from_dict(
        {
            "uri": "tcp://10.0.0.1:55002",
            "enable_zeroconf": True,
            "zeroconf_name": "asr",
            "web_server": True,
            "web_server_host": "0.0.0.0",
            "web_server_port": 5001,
            "web_server_allow": ["10.0.0.0/8"],
        }
    )
    assert config.uri == "tcp://10.0.0.1:55002"
    assert config.enable_zeroconf is True
    assert config.zeroconf_name == "asr"
    assert config.web_server is True
    assert config.web_server_host == "0.0.0.0"
    assert config.web_server_port == 5001
    assert config.web_server_allow == ["10.0.0.0/8"]


def test_from_args_cli_overrides_new_fields():
    config = Config.from_args(
        None, uri="tcp://127.0.0.1:55009", enable_zeroconf=True, web_server=True
    )
    assert config.uri == "tcp://127.0.0.1:55009"
    assert config.enable_zeroconf is True
    assert config.web_server is True


def test_from_args_env_var_applied(monkeypatch):
    monkeypatch.setenv("WYO_URI", "tcp://127.0.0.1:55007")
    monkeypatch.setenv("WYO_ENABLE_ZEROCONF", "true")
    monkeypatch.setenv("WYO_WEB_SERVER_PORT", "5002")
    monkeypatch.setenv("WYO_WEB_SERVER_ALLOW", "10.0.0.1,192.168.1.0/24")
    config = Config.from_args(None)
    assert config.uri == "tcp://127.0.0.1:55007"
    assert config.enable_zeroconf is True
    assert config.web_server_port == 5002
    assert config.web_server_allow == ["10.0.0.1", "192.168.1.0/24"]


def test_from_args_cli_beats_env(monkeypatch):
    monkeypatch.setenv("WYO_URI", "tcp://127.0.0.1:55007")
    config = Config.from_args(None, uri="tcp://127.0.0.1:55009")
    assert config.uri == "tcp://127.0.0.1:55009"
