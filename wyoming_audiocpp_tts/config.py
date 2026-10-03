"""Configuration for the Wyoming audio.cpp TTS bridge.

Configuration is layered, later layers win in this order: defaults (the
dataclass field values), then ``config.json`` with project settings and a
``tts_voices`` list of voice objects, then ``WYO_<FIELD>`` environment
variables where each value is upper-cased to match its dataclass name so a
container can configure without flags or an edit here; finally command-line
overrides on top.
"""

from __future__ import annotations

import os
import json
from dataclasses import dataclass, field, fields
from pathlib import Path
from typing import Any, Dict, List, Optional

DEFAULT_CONFIG_PATH = Path("config.json")
DEFAULT_URI = "tcp://0.0.0.0:10200"
DEFAULT_AUDIOCPP_URI = "http://localhost:8080"
DEFAULT_ASR_MODEL = "hviske"
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
class Config:
    """Resolved configuration for the Wyoming TTS bridge.

    ``Config.from_args`` is the entry point; it produces a fully resolved object
    that the server and CLI consume. Voices come only from config.json; no CLI
    flags for model/voice params.
    """

    audiocpp_uri: str = DEFAULT_AUDIOCPP_URI
    """Base URI of the audio.cpp HTTP server, e.g. ``http://localhost:8080``."""

    tts_voices: List[VoiceConfig] = field(default_factory=lambda: [VoiceConfig()])
    """List of TTS voices. Defaults to one omnivoice voice."""

    uri: str = DEFAULT_URI
    """Wyoming TCP bind, e.g. ``tcp://0.0.0.0:10200``."""

    enable_zeroconf: bool = False
    """Whether to register mDNS ``_wyoming._tcp.local.`` discovery."""

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
        """Full speech endpoint URL, joining the base URI and the endpoint.

        The URI's trailing slash is stripped so the join never produces a
        double slash.
        """
        uri = self.audiocpp_uri.rstrip("/")
        return f"{uri}/{_SPEECH_ENDPOINT.lstrip('/')}"

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Config":
        """Build config from a dict, reading ``tts_voices`` as a list."""
        voices_data = data.get("tts_voices")
        if isinstance(voices_data, list) and voices_data:
            voices = [VoiceConfig.from_dict(v) for v in voices_data]
        else:
            voices = [VoiceConfig()]
        return cls(
            audiocpp_uri=data.get("audiocpp_uri", DEFAULT_AUDIOCPP_URI),
            tts_voices=voices,
        )

    def _apply_env(self) -> "Config":
        """Return a copy of self with ``WYO_<FIELD>`` env vars applied.

        Top-level fields only; voices come from config.json.
        """
        result = self
        if "WYO_AUDIOPCPP_URI" in os.environ:
            result.audiocpp_uri = os.environ["WYO_AUDIOPCPP_URI"]
        return result

    @classmethod
    def from_args(cls, config_path: Optional[Path] = None, **overrides: Any) -> "Config":
        """Build config: config.json (if present), then env vars, then CLI.

        None override values are ignored, so a missing flag keeps the
        environment/config.json value (which itself defaults if absent).
        Voices come only from config.json; no CLI flags for model/voice params.
        """
        data: Dict[str, Any] = {}
        if config_path is not None:
            path = Path(config_path)
            if path.exists():
                data = json.loads(path.read_text(encoding="utf-8"))

        config = cls.from_dict(data)
        config = config._apply_env()

        for key, value in overrides.items():
            if value is not None and hasattr(config, key):
                setattr(config, key, value)

        config.validate()
        return config

    def validate(self) -> None:
        """Validate the resolved config, raising ``ValueError`` on a bad value.

        Checks run in a fixed order so callers get the first problem found.
        """
        if not self.tts_voices:
            raise ValueError("No TTS voices configured")
        for voice in self.tts_voices:
            if not voice.model:
                raise ValueError("tts_voices[].model must be set")
        if not self.audiocpp_uri.startswith(("http://", "https://")):
            raise ValueError(f"audiocpp_uri scheme must be http or https: {self.audiocpp_uri}")
        if self.tts_web_server and self.tts_web_server_port <= 0:
            raise ValueError("tts_web_server_port must be > 0 when tts_web_server is enabled")
