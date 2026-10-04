"""Launch the real Wyoming bridges against audio.cpp for playground smoke tests."""

from __future__ import annotations

import logging
import os
import subprocess
import time
from pathlib import Path

logging.disable(logging.CRITICAL)
HERE = Path(__file__).resolve().parent.parent
_PROCESSES: list[subprocess.Popen] = []


def _probe(port: int, path: str, timeout: float = 1.0) -> bool:
    import requests

    try:
        response = requests.get(f"http://127.0.0.1:{port}{path}", timeout=timeout)
        return response.status_code < 500
    except requests.RequestException:
        return False


def launch(
    tts_port: int = 11201,
    asr_port: int = 11301,
    *,
    audiocpp_uri: str | None = None,
    **flags,
) -> None:
    """Start both bridges and wait until their HTTP endpoints answer."""
    global _PROCESSES
    uri_args = ["--audiocpp-uri", audiocpp_uri] if audiocpp_uri else []
    _PROCESSES = [
        subprocess.Popen(
            [
                os.sys.executable,
                "-m",
                "wyoming_audiocpp_tts",
                "--tts-uri",
                f"tcp://127.0.0.1:{tts_port}",
                "--config",
                str(HERE.parent / "config.example.json"),
                *uri_args,
                *flags,
            ],
            cwd=str(HERE.parent),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        ),
        # The ASR bridge is a Wyoming TCP service; its demo HTTP surface
        # (--web-server) is what the playground talks to.
        subprocess.Popen(
            [
                os.sys.executable,
                "-m",
                "wyoming_audiocpp_asr",
                "--asr-uri",
                f"tcp://127.0.0.1:{asr_port + 1}",
                "--web-server",
                "--web-server-host",
                "127.0.0.1",
                "--web-server-port",
                str(asr_port),
                "--config",
                str(HERE.parent / "config.example.json"),
                *uri_args,
                *flags,
            ],
            cwd=str(HERE.parent),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        ),
    ]
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        if _probe(tts_port, "/") and _probe(asr_port, "/api/info"):
            return
        if any(process.poll() is not None for process in _PROCESSES):
            break
        time.sleep(0.1)
    shutdown()
    raise RuntimeError("real bridges did not become ready")


import signal


def shutdown() -> None:
    global _PROCESSES
    for process in _PROCESSES:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()
                try:
                    process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    process.send_signal(signal.SIGKILL)
                    process.wait(timeout=1)
    _PROCESSES = []
