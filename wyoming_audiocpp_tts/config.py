"""Configuration for the Wyoming audio.cpp TTS bridge.

Configuration is layered, later layers win in this order: defaults (the
dataclass field values), then ``config.json`` with project settings and voice
overrides as a ``tts_voice`` object plus per-scalar fields prefixed by
``tts_voice0_<field>``, then ``WYO_<FIELD>`` environment variables where each
value is upper-cased to match its dataclass name so a container can configure
without flags or an edit here; finally command-line overrides on top.
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

# Fields audio.cpp accepts on the speech endpoint.
_VOICE_FLAG_PREFIX = "tts_voice0_"
_SCALAR_FIELDS = ("model", "name", "language", "speed", "instruct")


@dataclass
class VoiceConfig:
    """Per-voice settings forwarded to audio.cpp's speech endpoint.

    ``model`` is the audio.cpp model id used for TTS; it defaults to omnivoice
    unless overridden in config.json or on the command line via --tts-voice0-model and similar scalar flags that add their values into this voice object keyed by tts_voice<index>-<field>.
    """

    model: str = DEFAULT_VOICE_MODEL
    """audio.cpp model id to use. Defaults to ``omnivoice``."""

    name: Optional[str] = None
    """Voice name passed to audio.cpp. ``None`` disables it."""

    language: Optional[str] = None
    """Language hint passed to audio.cpp. ``None`` disables it."""

    speed: Optional[float] = None
    """Speech rate multiplier. ``None`` disables it."""

    instruct: Optional[str] = None
    """Instruction string passed to audio.cpp. ``None`` disables it."""

    extra: Dict[str, Any] = field(default_factory=dict)
    """Extra audio.cpp ``options`` keys, e.g. ``seed``. Flattened verbatim."""

    def request_body(self, input: str) -> Dict[str, Any]:
        """Build the audio.cpp speech request body for ``input``.

        Always includes ``model`` and ``input``. ``language`` and ``speed`` are
        included only when set (``speed`` coerced to a number). ``instruct`` and
        any populated ``extra`` keys are collected into a single ``options``
        object; the object is omitted when it would be empty. The voice ``name``
        is for Home Assistant's service info and is never sent to audio.cpp.
        """
        body: Dict[str, Any] = {"model": self.model, "input": input}
        if self.language is not None:
            body["language"] = self.language
        if self.speed is not None:
            body["speed"] = float(self.speed)
        options: Dict[str, Any] = {}
        if self.instruct is not None:
            options["instruct"] = self.instruct
        if self.extra:
            options.update(self.extra)
        if options:
            body["options"] = options
        return body

    def to_dict(self) -> Dict[str, Any]:
        """Return the full voice mapping, all keys present (``None`` when unset)."""
        return {
            "model": self.model,
            "name": self.name,
            "language": self.language,
            "speed": self.speed,
            "instruct": self.instruct,
            "extra": self.extra,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "VoiceConfig":
        """Build a VoiceConfig from a dict, applying defaults for missing keys."""
        result = cls()
        for key in ("model", "name", "language", "speed", "instruct"):
            if key in data:
                setattr(result, key, data[key])
        if "extra" in data:
            result.extra = dict(data["extra"])
        return result


@dataclass
class Config:
    """Resolved configuration for the Wyoming TTS bridge.

    ``Config.from_args`` is the entry point; it produces a fully resolved object
    that the server and CLI consume.
    """

    audiocpp_uri: str = DEFAULT_AUDIOCPP_URI
    """Base URI of the audio.cpp HTTP server, e.g. ``http://localhost:8080``."""

    asr_model: str = DEFAULT_ASR_MODEL
    """audio.cpp ASR model id. Defaults to ``hviske``."""

    tts_voice: Optional[VoiceConfig] = None
    """Default TTS voice. ``None`` disables TTS until one is configured."""

    uri: str = DEFAULT_URI
    """Wyoming TCP bind, e.g. ``tcp://0.0.0.0:10200``."""

    enable_zeroconf: bool = False
    """Whether to register mDNS ``_wyoming._tcp.local.`` discovery."""

    zeroconf_name: Optional[str] = None
    """mDNS service name. Defaults to the URI host, else ``wyoming-audiocpp-tts``."""

    web_server: bool = False
    """Whether to also start the demo Flask web server."""

    web_server_host: str = "127.0.0.1"
    """Interface for the demo web server."""

    web_server_port: int = 5001
    """Port for the demo web server."""

    web_server_allow: Optional[List[str]] = None
    """IP addresses/CIDRs the demo web server may bind to, or ``None`` for all."""

    @property
    def tts_endpoint(self) -> str:
        """Full speech endpoint URL, joining the base URI and the endpoint.

        The URI's trailing slash is stripped so the join never produces a
        double slash.
        """
        uri = self.audiocpp_uri.rstrip("/")
        return f"{uri}/{_SPEECH_ENDPOINT.lstrip('/')}"

    @staticmethod
    def _merge_voice(current: Optional[VoiceConfig], overrides: Dict[str, Any]) -> VoiceConfig:
        """Merge ``overrides`` onto ``current``; leave unset fields untouched.

        ``extra`` merges additively (existing keys preserved); scalar fields are
        replaced only when present in ``overrides``.
        """
        if current is None:
            base = VoiceConfig()
        else:
            base = VoiceConfig(
                model=current.model,
                name=current.name,
                language=current.language,
                speed=current.speed,
                instruct=current.instruct,
                extra=dict(current.extra),
            )
        for key, value in overrides.items():
            if key == "extra":
                base.extra = {**base.extra, **value}
            elif hasattr(base, key):
                setattr(base, key, value)
        return base

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Config":
        """Build config from a dict, converting a nested ``tts_voice`` mapping."""
        voice_data = data.get("tts_voice")
        voice = VoiceConfig.from_dict(voice_data) if isinstance(voice_data, dict) else None
        return cls(
            audiocpp_uri=data.get("audiocpp_uri", DEFAULT_AUDIOCPP_URI),
            asr_model=data.get("asr_model", DEFAULT_ASR_MODEL),
            tts_voice=voice,
        )

    def _apply_env(self) -> "Config":
        """Return a copy of self with ``WYO_<FIELD>`` env vars applied.

        Top-level fields and voice scalar fields are read from the environment
        where each key is upper-cased to match the dataclass field name.
        """
        result = self
        for field_name in ("audiocpp_uri", "asr_model"):
            env_key = f"WYO_{field_name.upper()}"
            if env_key in os.environ:
                setattr(result, field_name, os.environ[env_key])

        voice_env: Dict[str, Any] = {}
        for field_name in _SCALAR_FIELDS:
            env_key = f"WYO_{field_name.upper()}"
            if env_key in os.environ:
                value = os.environ[env_key]
                voice_env[field_name] = float(value) if field_name == "speed" else value
        if voice_env:
            current = self.tts_voice if self.tts_voice is not None else VoiceConfig()
            merged = self._merge_voice(current, voice_env)
            result.tts_voice = merged
        return result

    @classmethod
    def from_args(cls, config_path: Optional[Path] = None, **overrides: Any) -> "Config":
        """Build config: config.json (if present), then env vars, then CLI.

        None override values are ignored, so a missing flag keeps the
        environment/config.json value (which itself defaults if absent).
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

        voice_overrides = overrides.pop("voice_overrides", None)
        if voice_overrides:
            stripped: Dict[str, Any] = {}
            for key, value in voice_overrides.items():
                if key.startswith(_VOICE_FLAG_PREFIX):
                    stripped[key[len(_VOICE_FLAG_PREFIX):]] = value
                else:
                    stripped[key] = value
            config.tts_voice = cls._merge_voice(config.tts_voice, stripped)

        config.validate()
        return config

    def validate(self) -> None:
        """Validate the resolved config, raising ``ValueError`` on a bad value.

        Checks run in a fixed order so callers get the first problem found.
        """
        if self.tts_voice is None:
            raise ValueError("No TTS voice configured")
        if not self.tts_voice.model:
            raise ValueError("tts_voice.model must be set")
        if not self.asr_model:
            raise ValueError("asr_model must be set")
        if not self.audiocpp_uri.startswith(("http://", "https://")):
            raise ValueError(f"audiocpp_uri scheme must be http or https: {self.audiocpp_uri}")
        if self.web_server and self.web_server_port <= 0:
            raise ValueError("web_server_port must be > 0 when web_server is enabled")
