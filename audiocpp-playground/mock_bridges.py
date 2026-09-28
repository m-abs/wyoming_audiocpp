"""Werkzeug-compatible mock Flask servers for the playground smoke test.

Two Flask apps stand in for the real Wyoming bridges, running on fixed ports:

* ``tts`` -- ``POST /api/tts`` returns a fake WAV stream; ``GET /`` returns metadata.
* ``asr`` -- ``POST /api/speech-to-text`` returns a canned transcription;
  ``GET /api/info`` returns a canned model list.

They share a Flask/Werkzeug install so the playground code paths are exercised.
"""

from __future__ import annotations

from flask import Flask, Response, jsonify, request


def _fake_wav(n: int = 44) -> bytes:
    return b"RIFF" + b"\x00" * 8 + b"WAVE" + b"\x00" * 8 + b"fma\xff" * n


# --- TTS bridge ----------------------------------------------------------------

tts = Flask("mock_tts")


@tts.route("/api/tts", methods=["POST"])
def api_tts():
    body = request.get_json(silent=True) or {}
    text = body.get("text")
    if not text:
        return jsonify({"error": "text is required"}), 400
    return Response(_fake_wav(), mimetype="audio/wav")


@tts.route("/")
def info():
    return jsonify({"name": "mock_tts"})


# --- ASR bridge ----------------------------------------------------------------

asr = Flask("mock_asr")


@asr.route("/api/speech-to-text", methods=["POST"])
def api_stt():
    # Mirror the patched real server: read the WAV from the multipart file part,
    # not the cached request.data (which is empty once the form is parsed).
    try:
        stored = request.files.get("file")
        data = stored.read() if stored is not None else request.get_data()
    except (KeyError, ValueError):
        data = request.get_data()
    if not data:
        return Response("empty request", status=400)
    lang = request.args.get("language")
    text = f"[mock-asr lang={lang or 'auto'}] {len(data)} bytes received"
    return jsonify({"text": text, "language": lang})


@asr.route("/api/info")
def models():
    return jsonify({"asr": [{"name": "whisper-1"}]})


@asr.route("/")
def info():
    return jsonify({"name": "mock_asr"})
