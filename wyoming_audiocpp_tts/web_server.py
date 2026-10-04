"""Demo browser UI for the audio.cpp TTS bridge.

This runs alongside the Wyoming TCP service. It reuses the existing Flask app
(``tts_server.create_app``) for the ``/api/tts`` and ``/api/status`` endpoints,
and adds a browser-facing ``GET /`` form plus ``/health`` and ``/api/status``
routes. The Wyoming service and the web server share one Flask app, so the web
server needs no audio.cpp logic of its own.
"""

from __future__ import annotations

import ipaddress
import logging
import socket
import threading
from typing import TYPE_CHECKING, Any, Iterable, List, Optional, Union

from werkzeug.serving import make_server

from . import tts_server

if TYPE_CHECKING:
    from flask import Flask

    from .config import Config


TTS_SERVICE_NAME = "wyoming-audiocpp-tts"

logger = logging.getLogger(__name__)


def _render_index() -> str:
    """Return the HTML page with a text area, voice dropdown, and a Synthesize button."""
    return """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>wyoming-audiocpp-tts</title>
<style>
  body { font-family: system-ui, sans-serif; margin: 2rem auto; max-width: 30rem; }
  label { display: block; margin-top: 1rem; }
  textarea { width: 100%; height: 12rem; box-sizing: border-box; }
  select { margin-top: 0.5rem; }
  button { margin-top: 1rem; padding: 0.5rem 1.25rem; cursor: pointer; }
  audio { display: block; margin-top: 1rem; width: 100%; }
</style>
</head>
<body>
<h1>audio.cpp TTS</h1>
<form id="form">
  <label>Text<textarea id="text" name="text" placeholder="Enter text to synthesize"></textarea></label>
  <label>Voice<select id="voice" name="voice"></select></label>
  <button type="submit">Synthesize</button>
</form>
<audio id="player" controls></audio>
<script>
fetch('/api/voices').then(r => r.json()).then(data => {
  const select = document.getElementById('voice');
  data.voices.forEach(v => {
    const opt = document.createElement('option');
    opt.value = v.name;
    opt.textContent = v.name + ' (' + v.model + ')';
    select.appendChild(opt);
  });
});
document.getElementById("form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const text = document.getElementById("text").value;
  const voice = document.getElementById("voice").value;
  try {
    const resp = await fetch('/api/tts', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({text: text, voice: voice}),
    });
    if (!resp.ok) { alert('Error: ' + resp.statusText); return; }
    const blob = await resp.blob();
    document.getElementById("player").src = URL.createObjectURL(blob);
  } catch (err) {
    alert('Request failed: ' + err);
  }
});
</script>
</body>
</html>
"""


def make_tts_web_server(config: "Config", flask_app: "Flask") -> "Flask":
    """Add browser routes to the existing Flask app."""
    from flask import Response, jsonify

    # The base app serves JSON metadata at ``/``; override it with the HTML form.
    flask_app.view_functions.pop("index", None)

    @flask_app.route("/", methods=["GET"])
    def index() -> Response:
        return Response(_render_index(), mimetype="text/html")

    @flask_app.route("/health", methods=["GET"])
    def health() -> Response:
        return jsonify({"status": "ok"})

    @flask_app.route("/api/status", methods=["GET"])
    def api_status() -> Response:
        return jsonify(
            {
                "service": TTS_SERVICE_NAME,
                "tts_voices": [v.voice_name for v in config.tts_voices],
            }
        )
    return flask_app


def run_web_server(flash_app: "Flask", host: str, port: int, allow_list: Optional[List[str]] = None) -> threading.Thread:
    """Run the Flask app in a daemon thread and return the thread.

    The listening socket is bound here, in the caller's thread, so a failure
    (port already in use, for one) raises ``OSError`` to the caller instead of
    killing the background thread just after we logged that the UI is available.
    We bind it rather than letting werkzeug do it because werkzeug's bind path
    prints to stderr and calls ``sys.exit(1)`` instead of raising. Handing it an
    already-bound ``fd`` skips that path entirely.

    ``allow_list`` is an optional list of IP addresses or CIDR ranges; when
    given, only requests from those networks are served (the UI has no
    authentication). An empty or ``None`` list serves any address that can
    connect.
    """
    logging.getLogger("werkzeug").setLevel(logging.ERROR)

    app = flash_app
    if allow_list:
        networks = [ipaddress.ip_network(value, strict=False) for value in allow_list]
        app = AllowListMiddleware(app, networks)

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind((host, port))
        sock.listen()
        server = make_server(host, port, app=app, fd=sock.fileno(), threaded=True)
    except BaseException:
        sock.close()
        raise

    thread = threading.Thread(
        target=server.serve_forever, name="wyoming-audiocpp-tts web server", daemon=True
    )
    thread.start()
    logger.info("Demo web server available on http://%s:%s", host, port)
    return thread


IPNetwork = Union[ipaddress.IPv4Network, ipaddress.IPv6Network]


def parse_allow_list(values: Iterable[str]) -> List[IPNetwork]:
    """Parse ``--web-server-allow`` entries into networks.

    Each entry is a single IP address or a CIDR range. Raises ``ValueError`` on
    a typo so the caller can fail at startup rather than silently rejecting
    every request.
    """
    return [ipaddress.ip_network(value, strict=False) for value in values]


class AllowListMiddleware:
    """Reject requests whose peer address is not in the allow list.

    The UI has no authentication of its own, so this closes the gap left by
    binding a routable address: only peers in the allow list are served. The
    address comes from ``REMOTE_ADDR`` -- the real TCP peer -- never from a
    forwarded header, which a client sets itself and could forge.
    """

    def __init__(self, app: "Flask", networks: List[IPNetwork]) -> None:
        self.app = app
        self.networks = networks

    def _is_allowed(self, remote_addr: Optional[str]) -> bool:
        """Return True if ``remote_addr`` is in the allow list.

        A dual-stack listener reports IPv4 peers as ``::ffff:a.b.c.d``, which
        would not match an IPv4 rule on its own, so mapped addresses are
        unwrapped before the membership check.
        """
        if not remote_addr:
            return False
        try:
            address = ipaddress.ip_address(remote_addr)
        except ValueError:
            return False
        mapped = getattr(address, "ipv4_mapped", None)
        if mapped is not None:
            address = mapped
        return any(address in network for network in self.networks)

    def __call__(self, environ, start_response) -> Any:
        client = environ.get("REMOTE_ADDR")
        if not self._is_allowed(client):
            from flask import Response

            start_response("403 Forbidden", [("Content-Type", "text/plain")])
            return [b"not allowed by --web-server-allow"]
        return self.app(environ, start_response)
