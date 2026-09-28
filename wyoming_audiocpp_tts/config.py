"""Configuration for the Wyoming audio.cpp TTS bridge.

Configuration is layered:

1. ``config.json`` with defaults and project settings.
2. Command-line flags, which override config.json.

audio.cpp is reached through its OpenAI-compatible speech endpoint. This bridge
wraps that endpoint and relays the audio result as a Wyoming TTS service.
"""

from __future__ import annotations

from dataclasses import dataclass, field, fields
from pathlib import Path
from typing import Any, Dict, Optional

DEFAULT_CONFIG_PATH = Path("config.json")
DEFAULT_AUDIOCPP_URI = "http://localhost:8080"
DEFAULT_ASR_MODEL = "hviske"
DEFAULT_VOICE_MODEL = "omnivoice"

# Fields audio.cpp accepts on the speech endpoint.
_SPEECH_ENDPOINT = "/v1/audio/speech"

# Prefix CLI ``--tts-voice0-<field>`` flags contribute to the single voice field.
VOICE_FLAG_PREFIX = "tts_voice0_"


@dataclass
class VoiceConfig:
    """Per-voice settings forwarded to audio.cpp's speech endpoint.

    ``model`` is the audio.cpp model id and the required field; ``name`` (the
    ``voice`` field), ``language``, ``speed``, ``instruct`` and ``extra`` (the
    ``options`` field) are optional per audio.cpp's request options.
    """

    model: str = DEFAULT_VOICE_MODEL
    """audio.cpp model id to use. Defaults to ``omnivoice``."""

    name: Optional[str] = None
    """audio.cpp ``voice`` field. ``None`` disables it."""

    language: Optional[str] = None
    """audio.cpp ``language`` field. ``None`` disables it."""

    speed: Optional[float] = None
    """audio.cpp ``speed`` field. ``None`` disables it."""

    instruct: Optional[str] = None

    extra: Dict[str, Any] = field(default_factory=dict)
    """Extra audio.cpp ``options`` keys, e.g. ``seed``. Flattened verbatim."""

    def request_body(self, input: str) -> Dict[str, Any]:
        """Build the audio.cpp speech request body for ``input``.
        ``model``, ``input``, ``voice``, ``language`` and ``speed`` are sent only
        when set; ``instruct`` and ``extra`` (as ``options``) are sent only when
        set, so a minimal ``VoiceConfig(model="omnivoice")`` produces
        ``{"model": ..., "input": ...}``.
        """
        body: Dict[str, Any] = {"model": self.model, "input": input}
        if self.name is not None:
            body["voice"] = self.name
        if self.language is not None:
            body["language"] = self.language
        if self.speed is not None:
            body["speed"] = self.speed
        if self.instruct is not None:
            body["instruct"] = self.instruct
        if self.extra:
            body["options"] = dict(self.extra)
        return body

    def to_dict(self) -> Dict[str, Any]:
        return {
            "model": self.model,
            "name": self.name,
            "language": self.language,
            "speed": self.speed,
            "instruct": self.instruct,
            "extra": dict(self.extra),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "VoiceConfig":
        return cls(
            model=data.get("model", cls.model),
            name=data.get("name"),
            language=data.get("language"),
            speed=data.get("speed"),
            instruct=data.get("instruct"),
            extra=dict(data.get("extra") or {}),
        )



@dataclass
class Config:
    """Resolved configuration for the Wyoming TTS bridge.

    ``audiocpp_uri`` is the audio.cpp base URI and the required field; ``asr_model``
    is the ASR model id (optional; empty disables it); ``tts_voice`` is the default
    voice (optional; ``None`` disables it).
    """

    audiocpp_uri: str = DEFAULT_AUDIOCPP_URI
    """Base URI of the audio.cpp HTTP server, e.g. ``http://localhost:8080``."""

    asr_model: Optional[str] = DEFAULT_ASR_MODEL
    """audio.cpp model id used for transcription. Defaults to ``hviske``."""

    tts_voice: Optional[VoiceConfig] = None
    """Default TTS voice. ``None`` disables it."""

    @property
    def tts_endpoint(self) -> str:
        """Full speech endpoint URL.

        ``audiocpp_uri`` is a slash-prefix base, so the endpoint is joined with
        exactly one ``/``; e.g. ``http://localhost:8080/v1/audio/speech``.
        """
        uri = self.audiocpp_uri.rstrip("/")
        return f"{uri}/{_SPEECH_ENDPOINT.lstrip('/')}"

    def to_dict(self) -> Dict[str, Any]:
        return {"audiocpp_uri": self.audiocpp_uri, "asr_model": self.asr_model, "tts_voice": self.tts_voice.to_dict()}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Config":
        result = cls()
        for key, value in data.items():
            if key in cls.__dataclass_fields__:
                field = cls.__dataclass_fields__[key]
                if field.type is not None and "VoiceConfig" in field.type and isinstance(value, dict):
                    setattr(result, key, VoiceConfig.from_dict(value))
                else:
                    setattr(result, key, value)
        return result

    def _apply(self, overrides: Dict[str, Any]) -> "Config":
        """Return a copy of ``self`` with ``overrides`` applied.

        Existing values (e.g. loaded from ``config.json``) are preserved; only the
        keys present in ``overrides`` are changed. The starting point is ``self``,
        not the defaults, so ``from_args`` keeps the file-loaded values unless a
        CLI flag supplies them.
        """
        result = self
        for key, value in overrides.items():
            if key in self.__dataclass_fields__:
                setattr(result, key, value)
        return result

    @classmethod
    def _merge_voice(cls, current: "VoiceConfig", overrides: Dict[str, Any]) -> "VoiceConfig":
        """Return a copy of ``current`` with ``overrides`` applied.

        ``overrides`` is the raw ``voice_overrides`` map (``model``, ``name``,
        ``language``, ``speed``, ``instruct``, plus ``extra``). Scalar voice
        fields are overridden only when present; ``extra`` is deep-merged.
        ``fields(VoiceConfig)`` is used explicitly rather than ``fields(cls)`` so
        this works whether called on ``VoiceConfig`` or ``Config``.
        """
        result = current if current is not None else VoiceConfig(model="")
        for field in fields(VoiceConfig):
            if field.name == "extra":
                continue
            value = overrides.get(field.name)
            if value is not None:
                setattr(result, field.name, value)
        if "extra" in overrides:
            result.extra.update(overrides["extra"])
        return result

    def validate(self) -> None:
        if not self.audiocpp_uri:
            raise ValueError("audiocpp_uri must be set")
        if not self.asr_model:
            raise ValueError("asr_model must be set")

        scheme, _, rest = self.audiocpp_uri.partition("://")
        if scheme not in ("http", "https"):
            raise ValueError(
                f"audiocpp_uri scheme must be http or https: {self.audiocpp_uri}"
            )

        if not self.tts_voice:
            raise ValueError("No TTS voice configured")


        if not self.tts_voice.model:
            raise ValueError("tts_voice.model must be set")
    @classmethod
    def from_args(
        cls,
        config_path: Optional[Path] = None,
        *,
        asr_model: Optional[str] = None,
        audiocpp_uri: Optional[str] = None,
        voice_overrides: Optional[Dict[str, Any]] = None,
    ) -> "Config":
        """Build config from an optional ``config.json`` then CLI overrides.

        ``None`` CLI values are ignored, so a missing flag keeps the config.json
        value (which itself defaults if absent). ``voice_overrides`` maps CLI
        ``--tts-voice0-<field>`` flags to voice fields; if any is present, the
        resulting voice replaces any file-supplied voice.
        """
        data = {}
        config_path = Path(config_path) if config_path is not None else None
        if config_path and config_path.exists():
            import json

            try:
                data = json.loads(config_path.read_text(encoding="utf-8"))
            except ValueError as exc:
                raise ValueError(f"{config_path}: {exc}") from exc
        config = cls.from_dict(data)

        overrides: Dict[str, Any] = {}
        if asr_model is not None:
            overrides["asr_model"] = asr_model
        if audiocpp_uri is not None:
            overrides["audiocpp_uri"] = audiocpp_uri
        if voice_overrides:
            # ``from_args`` receives CLI overrides keyed with the
            # ``tts_voice0_`` prefix; ``_merge_voice`` works with the plain
            # voice field names, so strip the prefix before merging.
            stripped = {
                (key[len(VOICE_FLAG_PREFIX):] if key.startswith(VOICE_FLAG_PREFIX) else key): value
                for key, value in voice_overrides.items()
            }
            voice = cls._merge_voice(config.tts_voice, stripped)
            overrides["tts_voice"] = voice

        config = config._apply(overrides)
        config.validate()
        return config
