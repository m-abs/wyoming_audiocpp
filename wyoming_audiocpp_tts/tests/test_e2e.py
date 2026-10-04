"""End-to-end tests for the Wyoming TTS TCP server.

These start a real ``AsyncTcpServer`` on a fixed port in a background thread and
talk to it over a socket the way Home Assistant / Rhasspy would, verifying the
handler is wired up (reader/writer) and that a ``Describe`` request is answered
with the service ``Info``.
"""

import io
import socket
import sys
import threading
import traceback
from urllib.parse import urlparse

from wyoming_audiocpp_tts.config import Config, VoiceConfig
from wyoming_audiocpp_tts.server import create_tcp_server
from wyoming.event import read_event, write_event
from wyoming.info import Describe

# Dedicated high port to avoid clashing with the default 10200 / other services.
SERVER_URI = "tcp://127.0.0.1:11231"


def _serialize(event):
    """Serialize an event to its wire bytes (JSON line + optional data)."""
    buf = io.BytesIO()
    write_event(event, buf)
    return buf.getvalue()


def _read_event(sock, timeout=5.0):
    """Read one Wyoming event from ``sock``, blocking up to ``timeout`` seconds.

    Bytes are accumulated in a buffer and re-parsed from a fresh reader on each
    pass, because the server may deliver an event's JSON line and its data in
    separate TCP segments (the way a real Wyoming client must handle them).
    """
    sock.settimeout(timeout)
    buf = b""
    while True:
        # Attempt to parse a complete event from the bytes received so far.
        reader = io.BytesIO(buf)
        event = read_event(reader)
        if event is not None:
            return event
        # Incomplete; need more bytes.
        try:
            chunk = sock.recv(8192)
        except socket.timeout:
            raise TimeoutError("timed out")
        if not chunk:
            return None
        buf += chunk


def _connect(config):
    host, port = urlparse(config.tts_uri).hostname, urlparse(config.tts_uri).port
    sock = socket.create_connection((host, port))
    return sock, host, port


def test_describe_returns_info():
    config = Config(
        tts_voices=[VoiceConfig(model="omnivoice")],
        tts_uri=SERVER_URI,
    )

    stop = threading.Event()
    error = {}

    def run():
        try:
            create_tcp_server(config)
        except Exception as exc:  # pragma: no cover - surfaced in the assertion
            error["exc"] = exc
            traceback.print_exc()
            print(f"SERVER THREAD ERROR: {exc!r}", file=sys.stderr)
        finally:
            stop.set()

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    try:
        assert not stop.wait(timeout=5), "server did not start in time"
    except AssertionError:
        if "exc" in error:
            raise error["exc"]
        raise

    print(f"SERVER STARTED on {SERVER_URI}; err={error.get('exc')!r}", file=sys.stderr)
    sock, host, port = _connect(config)
    print(f"CONNECTED to {host}:{port}", file=sys.stderr)
    try:
        sock.sendall(_serialize(Describe().event()))
        event = _read_event(sock)
    finally:
        sock.close()

    assert event is not None
    assert event.type == "info"

    program = event.data["tts"][0]
    assert program["name"] == "Wyoming Audio.cpp - tts"
    assert program["installed"] is True
    assert program["supports_synthesize_streaming"] is True
    assert len(program["voices"]) == 1
    assert program["voices"][0]["name"] == "omnivoice"
