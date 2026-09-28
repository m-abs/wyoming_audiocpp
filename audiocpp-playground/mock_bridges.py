"""Werkzeug-compatible mock Flask servers for the playground smoke test.

Two Flask apps stand in for the real Wyoming bridges, running on fixed ports:

* ``tts`` -- ``POST /api/tts`` returns a fake WAV stream; ``GET /`` returns metadata.
* ``asr`` -- ``POST /api/speech-to-text`` returns a canned transcription;
  ``GET /api/info`` returns a canned model list.

Both attach an ``Access-Control-Allow-Origin: *`` hook so the cross-origin
Next.js playground can call them. They share a Flask/Werkzeug install so the
playground code paths are exercised.
"""

from __future__ import annotations

from flask import Flask, Response, jsonify, request


def cors(resp):
    resp.headers["Access-Control-Allow-Origin"] = "*"
    return resp


def _fake_wav(n: int = 44) -> bytes:
    return b"RIFF" + b"\x00" * 8 + b"WAVE" + b"\x00" * 8 + b"fma\xff" * n


# --- TTS bridge ----------------------------------------------------------------

tts = Flask("mock_tts")


@tts.after_request
def _tts_cors(resp):
    return cors(resp)


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


@asr.after_request
def _asr_cors(resp):
    return cors(resp)


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


def _serve(app, host, port):
    from werkzeug.serving import make_server
    srv = make_server(host, port, app, threaded=True)
    srv.serve_forever()


def main():
    import argparse
    p = argparse.ArgumentParser(description="Run playground mock bridges")
    p.add_argument("--tts-port", type=int, default=11201)
    p.add_argument("--asr-port", type=int, default=11301)
    a = p.parse_args()
    import threading
    t = threading.Thread(target=_serve, args=(asr, "127.0.0.1", a.asr_port), daemon=True)
    t.start()
    t = threading.Thread(target=_serve, args=(tts, "127.0.0.1", a.tts_port), daemon=True)
    t.start()
    print("mock_tts listening on http://127.0.0.1:%d" % a.tts_port, flush=True)
    print("mock_asr listening on http://127.0.0.1:%d" % a.asr_port, flush=True)
