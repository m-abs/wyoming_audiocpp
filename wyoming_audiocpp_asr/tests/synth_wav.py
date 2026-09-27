"""Helpers to build minimal WAV payloads for tests."""

from __future__ import annotations

import io
import wave


def make_wav(
    *,
    rate: int = 16000,
    width: int = 2,
    channels: int = 1,
    samples: bytes = b"",
    endian: str = "little",
) -> bytes:
    """Build a WAV payload from raw PCM ``samples``."""
    pcm = samples if samples else _silence(rate, width, channels, 0.1)
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(channels)
        wav.setsampwidth(width)
        wav.setframerate(rate)
        wav.writeframes(pcm)
    return buffer.getvalue()


def _silence(rate: int, width: int, channels: int, seconds: float) -> bytes:
    sample_width = width * channels
    num_frames = int(seconds * rate)
    sample = bytes([0] * sample_width)
    return sample * num_frames


def make_wav_text(text: str, rate: int = 16000) -> bytes:
    """Encode text to bytes then wrap as a WAV payload.

    The text is not meaningful speech; audio.cpp would transcribe the raw bytes
    as audio. Used only to exercise the bridge request/response path.
    """
    import base64

    payload = base64.b64encode(text.encode("utf-8"))
    return make_wav(samples=payload, rate=rate)
