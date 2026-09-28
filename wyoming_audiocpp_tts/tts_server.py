"""Wyoming TTS HTTP server bridging to audio.cpp.

audio.cpp is an OpenAI-compatible HTTP server, not a Wyoming service, so this
bridge converts between the two on every request. It forwards speech requests
to ``<audiocpp_uri>/v1/audio/speech`` and relays the audio bytes back to Wyoming
clients.

Endpoints:

* ``POST /api/tts`` -- synthesize audio from the ``text`` field.
* ``GET /`` -- service metadata (name, models, voice).
"""

from __future__ import annotations

import logging

from flask import Flask, Response, jsonify, request

from . import audiocpp_client
from .config import Config

logger = logging.getLogger("wyoming_audiocpp_tts")

SERVICE_NAME = "wyoming_audiocpp_tts"


def create_app(config: Config) -> Flask:
    """Build the Flask application."""
    app = Flask("wyoming_audiocpp_tts")
    app.config["TTS_ENDPOINT"] = config.tts_endpoint
    app.config["TTS_VOICE"] = config.tts_voice
    app.config["ASR_MODEL"] = config.asr_model

    @app.route("/api/tts", methods=["POST"])
    def api_tts() -> Response:
        body = request.get_json(silent=True) or {}
        text = body.get("text")
        if not text:
            return jsonify(error="text is required"), 400

        try:
            audio = audiocpp_client.text_to_speech(
                app.config["TTS_ENDPOINT"],
                app.config["TTS_VOICE"],
                text=text,
            )
        except Exception as exc:  # noqa: BLE001 - upstream failure is always 502
            logger.exception("audio.cpp speech request failed")
            return Response(str(exc), status=502, mimetype="text/plain")

        return Response(audio, mimetype="audio/wav")

    @app.route("/", methods=["GET"])
    def index() -> Response:
        voice = app.config["TTS_VOICE"]
        return jsonify(
            {
                "name": SERVICE_NAME,
                "tts_model": voice.model if voice is not None else None,
                "tts_name": voice.name if voice is not None else None,
                "asr_model": app.config["ASR_MODEL"],
            }
        )

    return app
