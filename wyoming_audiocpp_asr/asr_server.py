"""Wyoming ASR HTTP server bridging to audio.cpp.

This service speaks the Wyoming ASR HTTP protocol so Wyoming clients (Rhasspy,
Home Assistant, ...) can use audio.cpp's transcription models. audio.cpp is an
OpenAI-compatible HTTP server, not a Wyoming service, so this bridge converts
between the two on every request.

Endpoints (the Wyoming ASR contract):

* ``POST /api/speech-to-text`` -- transcribe a WAV upload to text.
* ``GET  /api/info`` -- list available ASR models.

Audio.cpp's transcription endpoint is ``POST /v1/audio/transcriptions`` and
returns ``{"text": ..., "language": ...}``.
"""

from __future__ import annotations

import logging
from typing import Any, Dict

from flask import Flask, Response, jsonify, request

from . import audiocpp_client
from .config import Config

logger = logging.getLogger("wyoming_audiocpp_asr")


def create_app(config: Config) -> Flask:
    """Build the Flask application."""
    app = Flask("wyoming_audiocpp_asr")
    @app.before_request
    def cors_preflight():
        if request.method == "OPTIONS":
            resp = Response(status=200)
            resp.headers["Access-Control-Allow-Origin"] = "*"
            resp.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
            resp.headers["Access-Control-Allow-Headers"] = "Content-Type"
            return resp

    @app.after_request
    def cors(resp):
        resp.headers["Access-Control-Allow-Origin"] = "*"
        resp.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
        resp.headers["Access-Control-Allow-Headers"] = "Content-Type"
        return resp

    @app.route("/api/info", methods=["GET"])
    def api_info() -> Response:
        return jsonify(fetch_programs(config))

    @app.route("/api/speech-to-text", methods=["POST"])
    def api_stt() -> Response:
        # A multipart upload (the normal client case) leaves ``request.data`` empty:
        # Werkzeug moves the file part into ``request.files`` while parsing, so the
        # cached raw body is empty by the time we read it. Read the bytes from there
        # to reach audio.cpp; fall back to the raw body for a non-file POST. This is
        # the single source of truth for the uploaded WAV bytes.
        try:
            stored = request.files.get("file")
            data = stored.read() if stored is not None else request.get_data()
        except (KeyError, ValueError):
            data = request.get_data()
        if not data:
            return Response("empty request", status=400)

        language = request.args.get("language")
        model = request.args.get("model") or config.asr_model
        endpoint = config.transcription_endpoint

        try:
            data = audiocpp_client.transcribe(endpoint, data, model, language)
        except Exception as error:  # noqa: BLE001 -- surface to Wyoming client
            logger.exception("audio.cpp transcription failed")
            return Response(f"error: {error}", status=502)

        return jsonify({"text": data.get("text", ""), "language": data.get("language")})

    @app.route("/")
    def index() -> Response:
        return jsonify(
            {
                "name": "wyoming_audiocpp_asr",
                "audiocpp_uri": config.audiocpp_uri,
                "audiocpp_model": config.asr_model,
                "audiocpp_language": config.asr_language,
            }
        )

    return app


def fetch_programs(config: Config) -> Dict[str, Any]:
    """List ASR programs available through the bridge (Wyoming ``Info``)."""
    from .asr_handler import build_asr_info

    return build_asr_info(config).to_dict()
