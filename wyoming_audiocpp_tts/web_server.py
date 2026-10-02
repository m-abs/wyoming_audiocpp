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


SERVICE_NAME = "wyoming-audiocpp-tts"

logger = logging.getLogger(__name__)


def _render_index() -> str:
    """Return the HTML page with a text area and a Synthesize button."""
    return (
        "<html lang=\"en\">\n"
        "<head>\n"
        "  <meta charset=\"utf-8\">\n"
        "  <title>Wyoming audio.cpp TTS</title>\n"
        "  <style>\n"
        "    body { font-family: sans-serif; margin: 2rem; }\n"
        "    textarea { width: 100%; height: 12rem; }\n"
        "    button { padding: 0.5rem 1rem; }\n"
        "  </style>\n"
        "</head>\n"
        "<body>\n"
        "  <h1>Wyoming audio.cpp TTS</h1>\n"
        "  <textarea id=\"text\" placeholder=\"Enter text to synthesize\"></textarea>\n"
        "  <br>\n"
        "  <button onclick=\"synthesize()\">Synthesize</button>\n"
        "  <audio id=\"player\" controls></audio>\n"
        "  <script>\n"
        "    async function synthesize() {\n"
        "      const text = document.getElementById('text').value;\n"
        "      const resp = await fetch('/api/tts', {\n"
        "        method: 'POST',\n"
        "        headers: {'Content-Type': 'application/json'},\n"
        "        body: JSON.stringify({text: text}),\n"
        "      });\n"
        "      if (!resp.ok) { alert('Error: ' + resp.statusText); return; }\n"
        "      const blob = await resp.blob();\n"
        "      const url = URL.createObjectURL(blob);\n"
        "      document.getElementById('player').src = url;\n"
        "    }\n"
        "  </script>\n"
        "</body>\n"
        "</html>\n"
    )


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
        voice = config.tts_voice
        return jsonify(
            {
                "service": SERVICE_NAME,
                "tts_model": voice.model if voice is not None else None,
                "tts_name": voice.name if voice is not None else None,
                "asr_model": config.asr_model,
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
