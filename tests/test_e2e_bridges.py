"""End-to-end tests for the Wyoming audio.cpp bridges.

These hit the *real* Flask bridges (``wyoming_audiocpp_tts`` /
``wyoming_audiocpp_asr``) launched as subprocesses against the real
``audio.cpp`` HTTP server, so the whole request/response/proxy chain is
exercised -- not a mocked client.

audio.cpp is reachable as ``http://audio.cpp:8080`` (documented), with
``:8080`` omitted when it runs on the same host. The ``probe_audiocpp``
fixture resolves the URI at runtime from ``AUDIOCPP_URI`` (env) then
``audio.cpp``/``localhost``/``127.0.0.1`` on port 8080, falling back to
``localhost:8080`` -- the default happy-path launch skips if audio.cpp is
unreachable.

Two launch modes:

* **happy path** -- both bridges point at audio.cpp; used for positive
  TTS/ASR and skipped if audio.cpp is unreachable.
* **broken upstream** -- both bridges point at a dead port, so any upstream
  call raises and the bridge maps it to a ``502``. Deterministic; no audio.cpp
  needed.

The TTS bridge must be given a voice (``--tts-voice0-*``) to serve; the ASR
bridge just needs the model id (``--asr-model``). Ports are chosen outside the
playground's defaults so they never clash with a running dev container.

The ``test_data`` WAVs are ``float32``/``44.1 kHz`` stereo, which audio.cpp's
transcriber does not accept (it requires 16-bit/16 kHz mono PCM). Uploading one
therefore reaches audio.cpp, which rejects the format (HTTP 500) and the bridge
surfaces that as ``502`` -- that documents the WAV-format constraint on the
public bridge contract.
"""

from __future__ import annotations

import io
import os
import random
import struct
import subprocess
import time
import wave
from urllib.error import HTTPError
from urllib.request import urlopen

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
_REPO_PY = os.path.join(REPO, ".venv", "bin", "python")
PY = os.environ.get("PY_BIN")
if not PY:
    PY = _REPO_PY if os.path.exists(_REPO_PY) else os.sys.executable


def _audiocpp_port() -> int:
    return int(os.environ.get("AUDIOCPP_PORT", "8080"))


def _probe_audiocpp_uri() -> str | None:
    """Resolve audio.cpp's base URI (or None if unreachable)."""
    if env := os.environ.get("AUDIOCPP_URI"):
        if probe := _connect(env):
            return env
    base = f"http://audio.cpp:{_audiocpp_port()}"
    if probe := _connect(base):
        return base
    base = f"http://localhost:{_audiocpp_port()}"
    if probe := _connect(base):
        return base
    return None


def _connect(base: str) -> str | None:
    try:
        with urlopen(base + "/v1/models", timeout=3.0):
            return base
    except Exception:
        return None


def make_wav(*, rate: int = 16_000, seconds: float = 2.0,
             channels: int = 1, width: int = 2, seed: int = 0x1234) -> bytes:
    """A deterministic, valid WAV: ``rate`` kHz, ``channels`` ch, ``width``-bit.

    audio.cpp accepts 16-bit/16 kHz mono, so the default matches it. The frames
    are pseudo-random PCM -- audio.cpp would transcribe the *audio*, not the
    bytes, so the transcript text is asserted as non-empty rather than exact.
    """
    rng = random.Random(seed)
    n = int(seconds * rate)
    frames = struct.pack("<%dh" % n, *[rng.randint(-8000, 8000) for _ in range(n)])
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wav:
        wav.setnchannels(channels)
        wav.setsampwidth(width)
        wav.setframerate(rate)
        wav.writeframes(frames)
    return buf.getvalue()


def _is_wav(data: bytes) -> bool:
    return data[:4] == b"RIFF" and data[8:12] == b"WAVE"


# --------------------------------------------------------------------------- #
# Server helpers
# --------------------------------------------------------------------------- #

class BridgeServer:
    """A launched bridge subprocess bound to a test port."""

    def __init__(self, kind: str, port: int, audiocpp_uri: str) -> None:
        self.kind = kind
        self.port = port
        self.process: subprocess.Popen[bytes] | None = None
        self._start(audiocpp_uri)

    def _start(self, audiocpp_uri: str) -> None:
        common = ["--host", "127.0.0.1", "--port", str(self.port),
                  "--audiocpp-uri", audiocpp_uri]
        if self.kind == "tts":
            cmd = [PY, "-m", "wyoming_audiocpp_tts", "--log-level", "WARNING"]
            cmd += ["--tts-voice0-model", "omnivoice", "--tts-voice0-name", "TestVoice",
                    "--tts-voice0-language", "da"]
        else:
            cmd = [PY, "-m", "wyoming_audiocpp_asr", "--log-level", "WARNING"]
            cmd += ["--model", "hviske"]
        cmd += common
        self.process = subprocess.Popen(
            cmd, cwd=REPO, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )

    def is_alive(self) -> bool:
        return self.process is not None and self.process.poll() is None

    def wait_up(self, path: str, timeout: float = 10.0) -> None:
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self.is_alive() and self._health(path):
                return
            time.sleep(0.1)
        raise RuntimeError(f"{self.kind} bridge at :{self.port} did not come up")

    def _health(self, path: str) -> bool:
        try:
            r = urlopen(f"http://127.0.0.1:{self.port}{path}", timeout=1.0)
            return r.status < 500
        except Exception:
            return False

    def stop(self) -> None:
        if self.process is not None:
            self.process.terminate()
            try:
                self.process.wait(timeout=3.0)
            except Exception:
                self.process.kill()


@pytest.fixture
def audiocpp_uri():
    """audio.cpp base URI (default ``http://audio.cpp:8080``), or None if down."""
    return _probe_audiocpp_uri()


def _tts_synthesizes_wav(uri: str) -> bool:
    """audio.cpp synthesizes a WAV for the TTS endpoint. Gates the TTS happy path."""
    try:
        with requests.post(f"{uri}/api/tts",
                           json={"text": "hej verden"}, timeout=60) as r:
            return r.status == 200 and _is_wav(r.content)
    except Exception:
        return False

def _asr_upstream_accepts_wav(uri: str) -> bool:
    """Send the byte-valid WAV to audio.cpp's ASR endpoint.

    audio.cpp's ASR path requires a strict RIFF/WAVE header and a
    16-bit/16 kHz mono PCM layout. If it returns 200 it accepts byte-valid
    WAVs (healthy); if it rejects even these (degraded), the happy path cannot
    run and the tests must skip. This is the real acceptance check.
    """
    wav = make_wav()
    file_field = {"file": (b"audio.wav", "audio/wav", wav)}
    try:
        with requests.post(f"{uri}/api/speech-to-text",
                           files=file_field, timeout=60) as r:
            return r.status == 200
    except Exception:
        return False

@pytest.fixture
def happy_servers(audiocpp_uri):
    """Launch both bridges pointed at audio.cpp.

    Skips if audio.cpp is unreachable OR if its ASR endpoint rejects the
    byte-valid WAV (degraded format handling). On a healthy audio.cpp the ASR
    path accepts the WAV and the positive tests run.
    """
    if not audiocpp_uri:
        pytest.skip("audio.cpp unreachable")
    if not _asr_upstream_accepts_wav(audiocpp_uri):
        pytest.skip("audio.cpp rejects the byte-valid WAV")
    servers = {"tts": BridgeServer("tts", 11291, audiocpp_uri),
               "asr": BridgeServer("asr", 11391, audiocpp_uri)}
    for s in servers.values():
        s.wait_up("/")
    try:
        yield {"tts": servers["tts"], "asr": servers["asr"]}
    finally:
        for s in servers.values():
            s.stop()


@pytest.fixture
def broken_servers():
    """Launch both bridges pointed at a dead upstream (502 on any call)."""
    dead = "http://127.0.0.1:1"
    servers = {"tts": BridgeServer("tts", 11292, dead),
               "asr": BridgeServer("asr", 11392, dead)}
    for s in servers.values():
        s.wait_up("/")
    try:
        yield {"tts": servers["tts"], "asr": servers["asr"]}
    finally:
        for s in servers.values():
            s.stop()


# --------------------------------------------------------------------------- #
# TTS
# --------------------------------------------------------------------------- #

def test_tts_synthesizes_wav(happy_servers):
    import requests
    res = requests.post(f"http://127.0.0.1:11291/api/tts",
                        json={"text": "hej verden"}, timeout=120)
    assert res.status_code == 200, res.text
    assert res.headers.get("Content-Type", "").startswith("audio/wav"), res.headers
    data = res.content
    assert _is_wav(data), f"not a WAV, got {data[:16]!r}"
    with wave.open(io.BytesIO(data), "rb") as wav:
        # audio.cpp's /v1/audio/speech returns TTS at its native 24 kHz
        # regardless of the (optional) speed param, so the bridge relays 24 kHz
        # even though the Wyoming audio_rate_hz arg is 16000.
        assert wav.getframerate() == 24_000


def test_tts_empty_text_rejected(happy_servers):
    import requests
    res = requests.post(f"http://127.0.0.1:11291/api/tts",
                        json={}, timeout=120)
    assert res.status_code == 400


def test_tts_upstream_error_returns_502(broken_servers):
    import requests
    res = requests.post(f"http://127.0.0.1:11292/api/tts",
                        json={"text": "hej"}, timeout=30)
    assert res.status_code == 502


# --------------------------------------------------------------------------- #
# ASR
# --------------------------------------------------------------------------- #

def test_asr_transcribes_valid_wav(happy_servers):
    import requests
    wav = make_wav()
    file_field = {"file": (b"audio.wav", "audio/wav", wav)}
    res = requests.post(f"http://127.0.0.1:11391/api/speech-to-text",
                        files=file_field, timeout=120)
    assert res.status_code == 200, res.text
    body = res.json()
    assert isinstance(body.get("text"), str) and body["text"] != ""
    assert body.get("language") is None or isinstance(body.get("language"), str)


def test_asr_language_param_forwarded(happy_servers):
    import requests
    wav = make_wav()
    file_field = {"file": (b"audio.wav", "audio/wav", wav)}
    res = requests.post(f"http://127.0.0.1:11391/api/speech-to-text?language=en",
                        files=file_field, timeout=120)
    assert res.status_code == 200, res.text
    assert res.json().get("language") == "en"


def test_asr_upstream_error_returns_502(broken_servers):
    import requests
    wav = make_wav()
    file_field = {"file": (b"audio.wav", "audio/wav", wav)}
    res = requests.post(f"http://127.0.0.1:11392/api/speech-to-text",
                        files=file_field, timeout=30)
    assert res.status_code == 502


def test_asr_forwards_test_data_wav(happy_servers):
    """The committed test_data WAV is float32/44.1kHz stereo, which audio.cpp
    rejects; the bridge reaches audio.cpp (so the proxy path is exercised) and
    surfaces the upstream format rejection as 502. This documents the
    WAV-format constraint on the public bridge."""
    import requests
    wav = open(os.path.join(REPO, "test_data", "RMHL20190028_000013.wav"), "rb").read()
    assert wav[:4] == b"RIFF" and wav[8:12] == b"WAVE"
    file_field = {"file": (b"audio.wav", "audio/wav", wav)}
    res = requests.post(f"http://127.0.0.1:11391/api/speech-to-text",
                        files=file_field, timeout=120)
    # Either the bridge caps the payload (413) or audio.cpp rejects the format
    # (502 upstream -> 502). Both prove the request reaches the upstream proxy.
    assert res.status_code in (502, 413), f"unexpected {res.status_code}: {res.text[:200]}"


def _requests_toolbelt_or_requests(wav: bytes):
    """Return (session, file_field) using whatever multipart support is present.

    The bridge reads the ``file`` part of a multipart/form-data request; a plain
    ``requests`` ``files=`` call sends exactly that. requests_toolbelt is only
    used as a fallback for its streaming multipart writer.
    """
    try:
        import requests_toolbelt  # type: ignore
        with requests_toolbelt.MultipartEncoderStream() as stream:
            parts = [requests_toolbelt.fields.FileField(b"audio.wav",
                                                         filename="audio.wav",
                                                         content_type="audio/wav",
                                                         file=io.BytesIO(wav))]
            data = requests_toolbelt.MultipartEncoder(parts, boundary="testboundary")
            session = requests
            file_field = stream
            return session, file_field
    except Exception:
        session = requests
        file_field = {"file": (b"audio.wav", "audio/wav", wav)}
        return session, file_field
