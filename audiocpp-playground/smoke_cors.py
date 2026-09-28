"""Smoke test: exercise the mock bridges' CORS headers over real HTTP."""

import argparse

import requests

from mock_bridges import asr, tts


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--tts-port", type=int, default=11201)
    p.add_argument("--asr-port", type=int, default=11301)
    a = p.parse_args()
    tts_port, asr_port = a.tts_port, a.asr_port

    from werkzeug.serving import make_server
    import threading

    threads = []

    def run(app, port):
        srv = make_server("127.0.0.1", port, app, threaded=True)
        threading.Thread(target=srv.serve_forever, daemon=True).start()

    run(asr, asr_port)
    run(tts, tts_port)

    try:
        ok = True

        # 1. ASR model list from the playground (the route we just fixed).
        r = requests.get(f"http://127.0.0.1:{asr_port}/api/info",
                         headers={"Origin": "http://127.0.0.1:11000"})
        cors = r.headers.get("Access-Control-Allow-Origin")
        print(f"GET  ASR:{asr_port}/api/info -> {r.status_code} cors={cors}")
        print(f"       body={r.json()}")
        if r.status_code != 200 or cors != "*":
            ok = False

        # 2. TTS from the playground origin (cross-origin POST).
        r = requests.post(f"http://127.0.0.1:{tts_port}/api/tts",
                          json={"text": "hej"},
                          headers={"Origin": "http://127.0.0.1:11000"})
        cors = r.headers.get("Access-Control-Allow-Origin")
        print(f"POST TTS:{tts_port}/api/tts -> {r.status_code} cors={cors}")
        if r.status_code != 200 or cors != "*":
            ok = False

        if ok:
            print("SMOKE: OK — CORS present on both cross-origin endpoints")
            return 0
        print("SMOKE: FAIL")
        return 1
    finally:
        for t in threads:
            t.join(timeout=2)


if __name__ == "__main__":
    raise SystemExit(main())
