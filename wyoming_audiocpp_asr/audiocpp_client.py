"""HTTP bridge to audio.cpp's transcription endpoint.

audio.cpp exposes an OpenAI-compatible ``POST /v1/audio/transcriptions`` endpoint
that accepts a WAV ``file`` part plus ``model`` and ``language`` fields, and
returns ``{"text": ..., "language": ...}``. This module is the only place that
talks to audio.cpp directly; it is kept free of Wyoming-specific code so it can
be tested without a running server.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

import logging

import requests

_logger = logging.getLogger("wyoming_audiocpp_asr")


def transcribe(
    endpoint: str,
    wav_bytes: bytes,
    model: str,
    language: Optional[str],
    *,
    timeout: float = 15.0,
) -> Dict[str, Any]:
    """Transcribe WAV bytes via audio.cpp and return the parsed JSON response.

    The caller is responsible for sending a well-formed 16-bit 16 kHz mono WAV
    (Wyoming ASR and this project prefer exactly that format). The bytes are sent
    inline as the ``file`` part of a multipart/form-data request, matching the
    OpenAI Whisper convention audio.cpp expects.
    """
    _logger.debug(
        "Transcribe request: endpoint=%s model=%s language=%s wav_size=%d",
        endpoint,
        model,
        language,
        len(wav_bytes),
    )
    files = {"file": ("audio.wav", wav_bytes, "audio/wav")}
    data = {"model": model}
    if language is not None:
        data["language"] = language

    try:
        response = requests.post(
            endpoint,
            data=data,
            files=files,
            timeout=timeout,
        )
        response.raise_for_status()
    except requests.exceptions.RequestException as exc:
        _logger.error(
            "audio.cpp transcribe request failed: %s\n  url: %s\n  model: %s\n  language: %s",
            exc,
            endpoint,
            model,
            language,
        )
        raise
    result = response.json()
    _logger.debug(
        "Transcribe response: text=%r language=%s",
        result.get("text"),
        result.get("language"),
    )
    return result
