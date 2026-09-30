"""Demo browser web server for the Wyoming audio.cpp ASR bridge.

Started only with ``--web-server`` (the default service is the Wyoming TCP
server in ``server.py``). Reuses ``asr_server.create_app`` -- the existing
``/api/speech-to-text`` and ``/api/info`` endpoints, unchanged -- and adds a
browser-facing form, a health check and a status endpoint, mirroring
``wyoming-piper``'s web UI add-on.

The Flask/werkzeug imports make this module depend on the ``web`` optional
dependencies; ``__main__.py`` reports a missing install at startup.
"""

from __future__ import annotations

import ipaddress
import logging
import socket
import threading
from typing import Any, Dict, Iterable, List, Optional, Sequence, Union

from flask import Flask, Response, jsonify, request
from werkzeug.serving import make_server

from .asr_server import create_app
from .config import Config

logger = logging.getLogger("wyoming_audiocpp_asr")

IPNetwork = Union[ipaddress.IPv4Network, ipaddress.IPv6Network]

INDEX_HTML = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>wyoming-audiocpp-asr</title>
<style>
  body { font-family: system-ui, sans-serif; margin: 2rem auto; max-width: 28rem; }
  label { display: block; margin-top: 1rem; }
  #result { margin-top: 1rem; padding: 1rem; background: #f4f4f4; white-space: pre-wrap; min-height: 1.5rem; }
  button { margin-top: 1rem; }
  #status { margin-top: 1.5rem; font-size: 0.85rem; color: #555; }
</style>
</head>
<body>
<h1>audio.cpp ASR</h1>
<form id="form">
  <label>Audio file (WAV)<input type="file" name="file" accept="audio/*" required></label>
  <label>Language (blank = auto-detect)<input type="text" name="language" placeholder="da"></label>
  <button type="submit">Transcribe</button>
</form>
<div id="result"></div>
<div id="status"></div>
<script>
document.getElementById("form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const result = document.getElementById("result");
  result.textContent = "Transcribing...";
  const form = new FormData(e.target);
  const language = form.get("language");
  const url = "/api/speech-to-text" + (language ? "?language=" + encodeURIComponent(language) : "");
  try {
    const res = await fetch(url, {method: "POST", body: form});
    const body = await res.json().catch(() => ({}));
    result.textContent = res.ok
      ? (body.text || "(empty)") + (body.language ? " [" + body.language + "]" : "")
      : "Error: " + (body.text || res.status);
  } catch (err) {
    result.textContent = "Request failed: " + err;
  }
});
fetch("/api/status").then((r) => r.json()).then((s) => {
  document.getElementById("status").textContent =
    s.service + " -- model: " + s.model + " -- language: " + s.language;
}).catch(() => {});
</script>
</body>
</html>
"""


def make_asr_web_server(config: Config) -> Flask:
    """Build the demo Flask app (browser UI on top of the HTTP bridge)."""
    app = create_app(config)

    # Swap the JSON index for the browser UI; the "/" rule keeps mapping to the
    # "index" endpoint, which resolves through view_functions at dispatch time.
    def index() -> Response:  # noqa: D103 -- route handler
        return Response(INDEX_HTML, mimetype="text/html")

    app.view_functions["index"] = index

    @app.route("/health", methods=["GET"])
    def health() -> Response:
        return jsonify({"status": "ok"})

    @app.route("/api/status", methods=["GET"])
    def status() -> Response:
        return jsonify(
            {
                "service": "wyoming-audiocpp-asr",
                "model": config.model,
                "language": config.language,
            }
        )

    # Applied last so a rejected peer never reaches routing. The UI has no
    # authentication of its own.
    if config.web_server_allow:
        app.wsgi_app = AllowListMiddleware(
            app.wsgi_app, parse_allow_list(config.web_server_allow)
        )

    return app


def run_web_server(flask_app: Flask, host: str, port: int) -> threading.Thread:
    """Run the Flask app in a daemon thread.

    The listening socket is bound here, in the caller's thread, so a failure
    (port already in use, for one) raises ``OSError`` to the caller instead of
    killing the background thread just after we logged that the UI is available.
    """
    logging.getLogger("werkzeug").setLevel(logging.ERROR)

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind((host, port))
        sock.listen()
        server = make_server(host, port, flask_app, threaded=True, fd=sock.fileno())
    except BaseException:
        sock.close()
        raise

    thread = threading.Thread(
        target=server.serve_forever, name="web-server", daemon=True
    )
    thread.start()
    logger.info("Web UI available on http://%s:%s", host, port)
    return thread


def parse_allow_list(values: Iterable[str]) -> List[IPNetwork]:
    """Parse allow-list entries, each a single address or a CIDR range.

    Raises ValueError on anything unparseable, so a typo is reported at startup
    rather than silently rejecting every request.
    """
    return [ipaddress.ip_network(value, strict=False) for value in values]


class AllowListMiddleware:
    """Reject requests whose peer address is not in the allow list.

    The address comes from ``REMOTE_ADDR`` -- the real TCP peer -- and never
    from a forwarded header, which a client sets itself and could forge.
    """

    def __init__(self, app: Any, networks: Sequence[IPNetwork]) -> None:
        self.app = app
        self.networks = list(networks)

    def __call__(self, environ: Dict[str, Any], start_response: Any) -> Any:
        remote_addr = environ.get("REMOTE_ADDR")
        if not self._is_allowed(remote_addr):
            logger.warning("Rejected web UI request from %s", remote_addr)
            body = b"Forbidden\n"
            start_response(
                "403 Forbidden",
                [
                    ("Content-Type", "text/plain; charset=utf-8"),
                    ("Content-Length", str(len(body))),
                ],
            )
            return [body]

        return self.app(environ, start_response)

    def _is_allowed(self, remote_addr: Optional[str]) -> bool:
        if not remote_addr:
            return False

        try:
            address: Any = ipaddress.ip_address(remote_addr)
        except ValueError:
            return False

        # A dual-stack listener reports IPv4 peers as ::ffff:a.b.c.d, which
        # would not match an IPv4 rule on its own.
        mapped = getattr(address, "ipv4_mapped", None)
        if mapped is not None:
            address = mapped

        return any(address in network for network in self.networks)
