"""HTTP bridge to audio.cpp's speech endpoint.

audio.cpp exposes an OpenAI-compatible ``POST /v1/audio/speech`` endpoint that
accepts a JSON body with ``model``, ``input`` and optional fields
(``voice``, ``language``, ``speed``, ``options``), and returns raw audio bytes.
This module is the only place that talks to audio.cpp directly; it is kept free
of Wyoming-specific code so it can be tested without a running server.
"""

from __future__ import annotations

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

    response = requests.post(endpoint, json=body, timeout=timeout)
    response.raise_for_status()
    return response.content
