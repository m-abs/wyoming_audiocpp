"""HTTP bridge to audio.cpp's speech endpoint.

audio.cpp exposes an OpenAI-compatible ``POST /v1/audio/speech`` endpoint that
accepts a JSON body with ``model``, ``input`` and optional fields
(``voice``, ``language``, ``speed``, ``options``), and returns raw audio bytes.
This module is the only place that talks to audio.cpp directly; it is kept free
of Wyoming-specific code so it can be tested without a running server.
"""

from __future__ import annotations

import sys
from typing import Any, Dict

import requests


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

    try:
        response = requests.post(endpoint, json=body, timeout=timeout)
        response.raise_for_status()
    except requests.exceptions.RequestException as exc:
        print(
            f"audio.cpp TTS request failed: {exc}\n"
            f"  url: {endpoint}\n"
            f"  body: {body}",
            file=sys.stderr,
        )
        raise
    return response.content


from collections.abc import Iterator


def synthesize(
    endpoint: str,
    voice: Any,
    text: str,
    *,
    chunk_size: int = 4096,
    timeout: float = 120.0,
) -> Iterator[bytes]:
    """Stream ``text`` audio from audio.cpp as successive ``bytes`` chunks.

    audio.cpp's speech endpoint streams the response in batches, so this yields
    each batch as it arrives rather than buffering the whole file. A response
    that is not ``2xx`` raises the upstream error (via ``raise_for_status``).
    """
    body = voice.request_body(text)

    try:
        response = requests.post(endpoint, json=body, stream=True, timeout=timeout)
        response.raise_for_status()
    except requests.exceptions.RequestException as exc:
        print(
            f"audio.cpp synthesize request failed: {exc}\n"
            f"  url: {endpoint}\n"
            f"  body: {body}",
            file=sys.stderr,
        )
        raise

    for chunk in response.iter_content(chunk_size=chunk_size):
        if chunk:
            yield chunk
