"""Configuration for the Wyoming audio.cpp ASR bridge.

Configuration is layered:

1. ``config.json`` with defaults and project settings.
2. Command-line flags, which override config.json.

audio.cpp is reached through its OpenAI-compatible transcription endpoint. The
bridge speaks the Wyoming event protocol to that endpoint and relays the result
as a Wyoming ASR service.
"""

from __future__ import annotations

from dataclasses import dataclass, fields
from pathlib import Path
from typing import Any, Dict, Optional

DEFAULT_CONFIG_PATH = Path("config.json")
DEFAULT_AUDIOCPP_URI = "http://localhost:8080"
DEFAULT_MODEL = "hviske"
DEFAULT_LANGUAGE = "da"

# Fields audio.cpp accepts on the transcription endpoint.
_AUDIOCPP_ENDPOINT = "/v1/audio/transcriptions"


@dataclass
class Config:
    """Resolved configuration for the Wyoming ASR bridge.

    Every value is final here; command-line overrides have already been merged.
    """

    audiocpp_uri: str = DEFAULT_AUDIOCPP_URI
    """Base URI of the audio.cpp HTTP server, e.g. ``http://localhost:8080``.

    The Wyoming service talks to ``<audiocpp_uri>/v1/audio/transcriptions``.
    """

    model: str = DEFAULT_MODEL
    """audio.cpp model id used for transcription. Defaults to ``hviske``."""

    language: Optional[str] = DEFAULT_LANGUAGE
    """Language hint passed to audio.cpp. ``None`` disables it."""

    @property
    def transcription_endpoint(self) -> str:
        """Full transcription endpoint URL.

        ``_AUDIOCPP_ENDPOINT`` is a slash-less path prefix, so the base URI and
        the endpoint are joined with exactly one ``/``.
        """
        uri = self.audiocpp_uri.rstrip("/")
        return f"{uri}/{_AUDIOCPP_ENDPOINT.lstrip('/')}"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "audiocpp_uri": self.audiocpp_uri,
            "model": self.model,
            "language": self.language,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Config":
        result = cls()
        for field in fields(cls):
            if field.name in data:
                setattr(result, field.name, data[field.name])
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

    def validate(self) -> None:
        if not self.audiocpp_uri:
            raise ValueError("audiocpp_uri must be set")
        if not self.model:
            raise ValueError("model must be set")

        scheme, _, rest = self.audiocpp_uri.partition("://")
        if scheme not in ("http", "https"):
            raise ValueError(
                f"audiocpp_uri scheme must be http or https: {self.audiocpp_uri}"
            )

    @classmethod
    def from_args(
        cls,
        config_path: Optional[Path] = None,
        *,
        audiocpp_uri: Optional[str] = None,
        model: Optional[str] = None,
        language: Optional[str] = None,
    ) -> "Config":
        """Build config from an optional ``config.json`` then CLI overrides.

        ``None`` CLI values are ignored, so a missing flag keeps the config.json
        value (which itself defaults if absent).
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
        overrides = {
            key: value
            for key, value in (
                ("audiocpp_uri", audiocpp_uri),
                ("model", model),
                ("language", language),
            )
            if value is not None
        }
        config = config._apply(overrides)
        config.validate()
        return config
