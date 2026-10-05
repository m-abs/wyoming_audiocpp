"""Wyoming TTS HTTP server bridging to audio.cpp.

audio.cpp is an OpenAI-compatible HTTP server, not a Wyoming service, so this
bridge converts between the two on every request. It forwards speech requests
to ``<audiocpp_uri>/v1/audio/speech`` and relays the audio bytes back to Wyoming
clients.

Endpoints:

* ``POST /api/tts`` -- synthesize audio from the ``text`` field, optionally selecting a voice by name.
* ``GET /api/voices`` -- list the configured voices.
* ``GET /`` -- service metadata (name, voices).
"""

from __future__ import annotations

import logging

from flask import Flask, Response, jsonify, request

from . import audiocpp_client
from .config import TtsConfig, VoiceConfig

logger = logging.getLogger("wyoming_audiocpp_tts")

TTS_SERVICE_NAME = "wyoming_audiocpp_tts"


def _find_voice(voices: list[VoiceConfig], name: str | None) -> VoiceConfig:
    """Select a voice by name; fall back to the first voice."""
    if name:
        for v in voices:
            if v.voice_name == name:
                return v
    return voices[0]


def create_app(config: TtsConfig) -> Flask:
    """Build the Flask application."""
    app = Flask("wyoming_audiocpp_tts")
    app.config["TTS_ENDPOINT"] = config.tts_endpoint
    app.config["TTS_VOICES"] = config.tts_voices

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

    @app.route("/api/tts", methods=["POST"])
    def api_tts() -> Response:
        body = request.get_json(silent=True) or {}
        text = body.get("text")
        if not text:
            return jsonify(error="text is required"), 400

        voice = _find_voice(app.config["TTS_VOICES"], body.get("voice"))

        try:
            audio = audiocpp_client.text_to_speech(
                app.config["TTS_ENDPOINT"],
                voice,
                text=text,
            )
        except Exception as exc:  # noqa: BLE001 - upstream failure is always 502
            logger.exception("audio.cpp speech request failed")
            return Response(str(exc), status=502, mimetype="text/plain")

        return Response(audio, mimetype="audio/wav")

    @app.route("/api/voices", methods=["GET"])
    def api_voices() -> Response:
        return jsonify({
            "voices": [
                {"name": v.voice_name, "model": v.model}
                for v in app.config["TTS_VOICES"]
            ]
        })

    @app.route("/", methods=["GET"])
    def index() -> Response:
        return jsonify(
            {
                "name": TTS_SERVICE_NAME,
                "tts_voices": [v.voice_name for v in app.config["TTS_VOICES"]],
            }
        )

    return app
