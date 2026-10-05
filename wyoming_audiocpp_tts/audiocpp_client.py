"""HTTP bridge to audio.cpp's speech endpoint.

audio.cpp exposes an OpenAI-compatible ``POST /v1/audio/speech`` endpoint that
accepts a JSON body with ``model``, ``input`` and optional fields
(``language``, ``speed``, ``options``), and returns raw audio bytes (a WAV
file). This module is the only place that talks to audio.cpp directly; it is
kept free of Wyoming-specific code so it can be tested without a running server.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from typing import Any, List

import logging

import requests

_logger = logging.getLogger("wyoming_audiocpp_tts")


@dataclass(frozen=True)
class WavFormat:
    """Audio format extracted from a WAV header."""

    sample_rate: int
    channels: int
    sampwidth: int  # bytes per sample (1 = 8-bit, 2 = 16-bit, 4 = 32-bit)

def _parse_wav_header(data: bytes) -> tuple[WavFormat, int]:
    """Parse a WAV header and return the audio format + data chunk offset.

    Walks through RIFF chunks to find the ``fmt `` chunk (audio parameters)
    and the ``data`` chunk offset. Returns ``(format, data_offset)``.
    Raises ``ValueError`` on a malformed header.
    """
    if len(data) < 12 or data[:4] != b"RIFF" or data[8:12] != b"WAVE":
        raise ValueError("not a WAV file")

    fmt: WavFormat | None = None
    data_offset: int | None = None

    # Walk chunks starting at offset 12.
    pos = 12
    while pos + 8 <= len(data):
        chunk_id = data[pos : pos + 4]
        chunk_size = struct.unpack("<I", data[pos + 4 : pos + 8])[0]
        body_start = pos + 8

        if chunk_id == b"fmt " and fmt is None:
            if chunk_size < 16:
                raise ValueError("fmt chunk too small")
            audio_format, channels, sample_rate, _, _, bits_per_sample = struct.unpack(
                "<HHIIHH", data[body_start : body_start + 16]
            )
            if audio_format != 1:
                raise ValueError(f"unsupported audio format {audio_format} (only PCM)")
            if bits_per_sample not in (8, 16, 32):
                raise ValueError(f"unsupported bit depth {bits_per_sample}")
            fmt = WavFormat(
                sample_rate=sample_rate,
                channels=channels,
                sampwidth=bits_per_sample // 8,
            )
        elif chunk_id == b"data" and data_offset is None:
            data_offset = body_start
            break

        pos = body_start + chunk_size
        # Chunks are word-aligned (pad to even size).
        if chunk_size % 2:
            pos += 1

    if fmt is None or data_offset is None:
        raise ValueError("WAV header missing fmt or data chunk")

    return fmt, data_offset


def text_to_speech(
    endpoint: str,
    voice: Any,
    text: str,
    *,
    timeout: float = 120.0,
) -> bytes:
    """Synthesize ``text`` via audio.cpp and return the raw audio bytes.

    ``voice`` is a ``VoiceConfig`` that produces the request body; the body is
    sent as the ``json`` argument of the multipart-free request. A response that
    is not ``2xx`` raises the upstream error (via ``raise_for_status``), so the
    caller (the server) decides what to return to the client.
    """
    body = voice.request_body(text)

    _logger.debug(
        "TTS request: endpoint=%s body=%s",
        endpoint,
        body,
    )
    try:
        response = requests.post(endpoint, json=body, timeout=timeout)
        response.raise_for_status()
    except requests.exceptions.RequestException as exc:
        _logger.error(
            "audio.cpp TTS request failed: %s\n  url: %s\n  body: %s",
            exc,
            endpoint,
            body,
        )
        raise
    _logger.debug(
        "TTS response: audio_size=%d",
        len(response.content),
    )
    return response.content


def synthesize(
    endpoint: str,
    voice: Any,
    text: str,
    *,
    timeout: float = 120.0,
) -> tuple[WavFormat, List[bytes]]:
    """Synthesize ``text`` via audio.cpp and return the format + PCM data.

    Returns a tuple ``(format, pcm_chunks)`` where ``format`` describes the
    audio (sample rate, channels, sample width) and ``pcm_chunks`` is a list
    of raw PCM byte strings with the WAV header stripped.

    A response that is not ``2xx`` raises the upstream error (via
    ``raise_for_status``).
    """
    body = voice.request_body(text)

    _logger.debug(
        "Synthesize request: endpoint=%s body=%s",
        endpoint,
        body,
    )
    try:
        response = requests.post(endpoint, json=body, timeout=timeout)
        response.raise_for_status()
    except requests.exceptions.RequestException as exc:
        _logger.error(
            "audio.cpp synthesize request failed: %s\n  url: %s\n  body: %s",
            exc,
            endpoint,
            body,
        )
        raise

    data = response.content
    fmt, data_offset = _parse_wav_header(data)
    pcm = data[data_offset:]

    # Split into 4 KB chunks so the handler can pace them to real-time.
    chunk_size = 4096
    chunks = [pcm[i : i + chunk_size] for i in range(0, len(pcm), chunk_size)]

    _logger.debug(
        "Synthesize response: format=%s pcm_size=%d chunks=%d",
        fmt,
        len(pcm),
        len(chunks),
    )

    return fmt, chunks
