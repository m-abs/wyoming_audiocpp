"""HTTP bridge to audio.cpp's transcription endpoint.

audio.cpp exposes an OpenAI-compatible ``POST /v1/audio/transcriptions`` endpoint
that accepts a WAV ``file`` part plus ``model`` and ``language`` fields, and
returns ``{"text": ..., "language": ...}``. This module is the only place that
talks to audio.cpp directly; it is kept free of Wyoming-specific code so it can
be tested without a running server.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

import requests


def transcribe(
    endpoint: str,
    wav_bytes: bytes,
    model: str,
    language: Optional[str],
    *,
    timeout: float = 120.0,
) -> Dict[str, Any]:
    """Transcribe WAV bytes via audio.cpp and return the parsed JSON response.

    The caller is responsible for sending a well-formed 16-bit 16 kHz mono WAV
    (Wyoming ASR and this project prefer exactly that format). The bytes are sent
    inline as the ``file`` part of a multipart/form-data request, matching the
    OpenAI Whisper convention audio.cpp expects.
    """
    files = {"file": ("audio.wav", _audio_type(wav_bytes), "audio/wav")}
    data = {"model": model}
    if language is not None:
        data["language"] = language

    response = requests.post(
        endpoint,
        data=data,
        files=files,
        timeout=timeout,
    )
    response.raise_for_status()
    return response.json()


def _audio_type(wav_bytes: bytes) -> str:
    """MIME type for an uploaded audio part.

    audio.cpp only accepts WAV, so the part is declared as ``audio/wav``. We rely
    on the caller having produced a WAV; if not, audio.cpp rejects it at decode.
    """
    return "audio/wav"
