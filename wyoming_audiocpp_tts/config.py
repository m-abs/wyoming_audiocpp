"""Configuration for the Wyoming audio.cpp TTS bridge.

Subclasses ``BridgeConfig`` from ``wyoming_audiocpp_common`` with TTS-specific
fields: voice list, bind URI, and demo web server settings. Voices come only
from config.json; no CLI flags for model/voice params.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, fields
from pathlib import Path
from typing import Any, Dict, List, Optional

from wyoming_audiocpp_common.config import BridgeConfig

DEFAULT_URI = "tcp://0.0.0.0:11201"
DEFAULT_VOICE_MODEL = "omnivoice"

_SPEECH_ENDPOINT = "/v1/audio/speech"


@dataclass
class VoiceConfig:
    """Per-voice settings forwarded to audio.cpp's speech endpoint.

    ``model`` is the audio.cpp model id used for TTS; it defaults to omnivoice
    unless overridden in config.json. ``options`` holds free-form model params,
    coerced by type on send (see ``params.py``).
    """

    model: str = DEFAULT_VOICE_MODEL
    """audio.cpp model id to use. Defaults to ``omnivoice``."""

    name: Optional[str] = None
    """Voice id; defaults to the model when unset."""

    language: Optional[str] = None
    """Language hint passed to audio.cpp. ``None`` disables it."""

    speed: Optional[float] = None
    """Speech rate multiplier. ``None`` disables it."""

    options: Dict[str, Any] = field(default_factory=dict)
    """Free-form model params forwarded verbatim to audio.cpp's ``options``."""

    @property
    def voice_name(self) -> str:
        return self.name if self.name else self.model

    def request_body(self, input: str) -> Dict[str, Any]:
        """Build the audio.cpp speech request body for ``input``.

        Always includes ``model`` and ``input``. ``language`` and ``speed`` are
        included only when set (``speed`` coerced to a number). ``options`` is
        included only when populated; each value is coerced by its declared type
        from audio.cpp's ``model_params.json`` so numbers are never sent as strings.
        """
        from . import params

        body: Dict[str, Any] = {"model": self.model, "input": input}
        if self.language is not None:
            body["language"] = self.language
        if self.speed is not None:
            body["speed"] = float(self.speed)
        if self.options:
            body["options"] = {
                k: params.coerce(self.model, k, v) for k, v in self.options.items()
            }
        return body

    def to_dict(self) -> Dict[str, Any]:
        """Return the full voice mapping, all keys present (``None`` when unset)."""
        return {
            "model": self.model,
            "name": self.name,
            "language": self.language,
            "speed": self.speed,
            "options": self.options,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "VoiceConfig":
        """Build a VoiceConfig from a dict, applying defaults for missing keys."""
        result = cls()
        for key in ("model", "name", "language", "speed"):
            if key in data:
                setattr(result, key, data[key])
        if "options" in data:
            result.options = dict(data["options"])
        return result


@dataclass
class TtsConfig(BridgeConfig):
    """Resolved configuration for the Wyoming TTS bridge.

    ``TtsConfig.from_args`` is the entry point; it produces a fully resolved
    object that the server and CLI consume. Voices come only from config.json;
    no CLI flags for model/voice params.
    """

    tts_voices: List[VoiceConfig] = field(default_factory=lambda: [VoiceConfig()])
    """List of TTS voices. Defaults to one omnivoice voice."""

    tts_uri: str = DEFAULT_URI
    """Wyoming TCP bind, e.g. ``tcp://0.0.0.0:11201``."""

    tts_web_server: bool = False
    """Whether to also start the demo Flask web server."""

    tts_web_server_host: str = "127.0.0.1"
    """Interface for the demo web server."""

    tts_web_server_port: int = 5001
    """Port for the demo web server."""

    tts_web_server_allow: Optional[List[str]] = None
    """IP addresses/CIDRs the demo web server may bind to, or ``None`` for all."""

    @property
    def tts_endpoint(self) -> str:
        """Full speech endpoint URL, joining the base URI and the endpoint."""
        return self.endpoint(_SPEECH_ENDPOINT)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TtsConfig":
        """Build config from a dict, reading ``tts_voices`` as a list."""
        voices_data = data.get("tts_voices")
        if isinstance(voices_data, list) and voices_data:
            voices = [VoiceConfig.from_dict(v) for v in voices_data]
        else:
            voices = [VoiceConfig()]
        result = cls(tts_voices=voices)
        for f in fields(cls):
            if f.name in data and f.name != "tts_voices":
                setattr(result, f.name, data[f.name])
        return result

    def validate(self) -> None:
        super().validate()
        if not self.tts_voices:
            raise ValueError("No TTS voices configured")
        for voice in self.tts_voices:
            if not voice.model:
                raise ValueError("tts_voices[].model must be set")
        if self.tts_web_server and self.tts_web_server_port <= 0:
            raise ValueError(
                "tts_web_server_port must be > 0 when tts_web_server is enabled"
            )
