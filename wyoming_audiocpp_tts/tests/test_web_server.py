"""Tests for the demo browser web server (opt-in via ``--web-server``).

The UI is a thin HTML form over the Flask app; these exercise the routes it
adds (``/``, ``/health``, ``/api/status``) and the peer-address allow list that
closes the gap left by binding a routable address.
"""

import ipaddress
from typing import Any, List, Optional

import pytest

pytest.importorskip("flask", reason="requires the 'web' optional dependencies")

from wyoming_audiocpp_tts.config import TtsConfig
from wyoming_audiocpp_tts.tts_server import create_app
from wyoming_audiocpp_tts.web_server import (
    AllowListMiddleware,
    make_tts_web_server,
    parse_allow_list,
)


def _config() -> TtsConfig:
    return TtsConfig.from_args(None)


def _client(config: TtsConfig, allow: Optional[List[str]] = None) -> Any:
    """Build a test client for the demo UI.

    ``make_tts_web_server`` adds the browser routes to the base app; when an
    allow list is given it wraps the app in ``AllowListMiddleware`` exactly as
    ``run_web_server`` does, so the peer-address check is exercised here rather
    than only on a live socket. A werkzeug test client (not Flask's) is used so
    requests pass through the middleware when present.
    """
    from werkzeug.test import Client

    app = create_app(config)
    make_tts_web_server(config, app)
    if allow:
        networks = [ipaddress.ip_network(value, strict=False) for value in allow]
        app = AllowListMiddleware(app, networks)
    return Client(app)


@pytest.fixture(name="client")
def client_fixture() -> Any:
    """A test client with no allow list (default behaviour)."""
    return _client(_config())


def test_index_serves_html_form(client: Any) -> None:
    """``/`` is the browser form, not the base app's JSON metadata."""
    response = client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers["Content-Type"]
    body = response.get_data(as_text=True)
    assert "<textarea id=\"text\"" in body
    assert "Synthesize" in body


def test_health(client: Any) -> None:
    assert client.get("/health").get_json() == {"status": "ok"}


def test_api_status_reports_config(client: Any) -> None:
    status = client.get("/api/status").get_json()
    assert status["service"] == "wyoming-audiocpp-tts"
    assert status["tts_voices"] == ["omnivoice"]


def test_base_app_index_is_overridden(client: Any) -> None:
    """The base app's JSON ``/`` must not leak past the HTML form."""
    response = client.get("/")
    # The form is HTML, so it must not be the base app's JSON object.
    assert "name" not in (response.get_json() or {})


def test_synthesize_post(client: Any) -> None:
    """POST ``{text}`` to ``/api/tts`` returns non-empty ``audio/wav``."""
    from unittest import mock

    from wyoming_audiocpp_tts import audiocpp_client

    def fake_post(url, json=None, timeout=None, **kwargs):
        response = mock.Mock()
        response.status_code = 200
        response.content = b"RIFF....WAVE"
        return response

    with mock.patch.object(audiocpp_client.requests, "post", side_effect=fake_post):
        response = client.post("/api/tts", json={"text": "Hello"})

    assert response.status_code == 200
    assert response.mimetype == "audio/wav"
    assert len(response.get_data()) > 0

def test_no_allow_list_serves_everyone(client: Any) -> None:
    """Default behaviour is unchanged, so existing setups keep working."""
    for remote_addr in ("10.0.0.5", "192.168.1.1"):
        assert _status(client, remote_addr) == 200


def test_allowed_address_is_served() -> None:
    client = _client(_config(), ["172.30.32.2"])
    assert _status(client, "172.30.32.2") == 200


@pytest.mark.parametrize(
    "remote_addr",
    [
        "10.0.0.5",
        "192.168.1.1",
        "172.30.32.3",
    ],
)
def test_other_addresses_are_rejected(remote_addr: str) -> None:
    client = _client(_config(), ["172.30.32.2"])
    assert _status(client, remote_addr) == 403


def test_cidr_range() -> None:
    client = _client(_config(), ["172.30.32.0/24"])
    assert _status(client, "172.30.32.9") == 200
    assert _status(client, "172.30.33.1") == 403


def test_several_entries() -> None:
    client = _client(_config(), ["172.30.32.2", "127.0.0.1"])
    assert _status(client, "172.30.32.2") == 200
    assert _status(client, "127.0.0.1") == 200
    assert _status(client, "10.0.0.5") == 403


def test_invalid_entry_is_reported() -> None:
    """__main__ turns this into a startup error rather than a silent deny-all."""
    with pytest.raises(ValueError):
        parse_allow_list(["172.30.32.999"])


def _status(client: Any, remote_addr: str) -> int:
    return client.get(
        "/api/status", environ_base={"REMOTE_ADDR": remote_addr}
    ).status_code
