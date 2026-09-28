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
