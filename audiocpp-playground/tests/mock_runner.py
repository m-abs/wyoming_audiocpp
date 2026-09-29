"""Launch werkzeug mock bridges for the playground e2e suite.

Mirrors src/lib/config.ts defaults (TTS /api/tts, ASR /api/speech-to-text,
/asr/info) so tests exercise the real client routing against controlled
responses -- no audio.cpp dependency.
"""

from __future__ import annotations

import argparse
import os
import sys
import threading

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mock_bridges import asr, tts  # noqa: E402
from werkzeug.serving import make_server  # noqa: E402

_tts_s = None
_asr_s = None


def _wait_until(port, path, timeout=3.0):
    import requests

    for _ in range(int(timeout / 0.1)):
        try:
            requests.get(f"http://127.0.0.1:{port}{path}", timeout=1.0)
            return
        except requests.RequestException:
            pass


def start(server):
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()


def launch(tts_port=11201, asr_port=11301):
    """Start mock bridges on the ports configured by the playground."""
    global _tts_s, _asr_s
    _tts_s = make_server("0.0.0.0", tts_port, tts, threaded=True)
    _asr_s = make_server("0.0.0.0", asr_port, asr, threaded=True)
    start(_tts_s)
    start(_asr_s)
    _wait_until(tts_port, "/")
    _wait_until(asr_port, "/api/info")
    print(f"mock TTS: http://127.0.0.1:{tts_port}", flush=True)
    print(f"mock ASR: http://127.0.0.1:{asr_port}", flush=True)


import signal
import time


def shutdown():
    global _tts_s, _asr_s
    for server in (_asr_s, _tts_s):
        if server is not None:
            server.shutdown()
            time.sleep(0.5)
    _tts_s, _asr_s = None, None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tts-port", type=int, default=11201)
    parser.add_argument("--asr-port", type=int, default=11301)
    args = parser.parse_args()
    launch(args.tts_port, args.asr_port)
    threading.Event().wait()


if __name__ == "__main__":
    main()
