"""Shared configuration base for the Wyoming audio.cpp bridges.

``BridgeConfig`` holds the fields and layered-resolution machinery common to
both the ASR and TTS bridges:

1. Defaults (the dataclass field defaults).
2. ``config.json`` with project settings.
3. Environment variables ``WYO_<FIELD>`` (the field name, upper-cased).
4. Command-line flags.

Subclasses add their own fields and override ``validate()`` for
package-specific checks. The generic ``_apply_env`` parser handles scalar
types (str, bool, int, float, Optional of those, List[str]) and skips
non-primitive types (e.g. ``List[VoiceConfig]``), which must come from
config.json only.
"""

from __future__ import annotations

import dataclasses
import json
import os
from dataclasses import dataclass, fields
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

DEFAULT_AUDIOCPP_URI = "http://localhost:8080"
ENV_PREFIX = "WYO_"

_BOOL_TRUE = {"1", "true", "yes", "on"}
_BOOL_FALSE = {"0", "false", "no", "off"}

# Types the generic env parser can handle. Anything else is skipped.
_SCALAR_TYPES = (
    "str",
    "bool",
    "int",
    "float",
    "Optional[str]",
    "Optional[bool]",
    "Optional[int]",
    "Optional[float]",
    "List[str]",
    "Optional[List[str]]",
)


def _parse_bool(value: str) -> bool:
    lowered = value.strip().lower()
    if lowered in _BOOL_TRUE:
        return True
    if lowered in _BOOL_FALSE:
        return False
    raise ValueError(f"cannot parse {value!r} as a boolean")


def _parse_int(value: str) -> int:
    try:
        return int(str(value).strip())
    except ValueError as exc:
        raise ValueError(f"cannot parse {value!r} as an integer") from exc


def _parse_env(type_str: str, value: str) -> Any:
    """Parse an environment string into the type of a ``BridgeConfig`` field.

    Returns the raw string for unrecognised types (the caller skips them).
    """
    if type_str in ("bool", "Optional[bool]"):
        return _parse_bool(value)
    if type_str in ("int", "Optional[int]"):
        return _parse_int(value)
    if type_str in ("float", "Optional[float]"):
        return float(value)
    if "List[" in type_str:
        return [item.strip() for item in value.split(",") if item.strip()]
    return value


@dataclass
class BridgeConfig:
    """Shared base configuration for a Wyoming audio.cpp bridge.

    Holds the fields common to both ASR and TTS bridges plus the layered
    resolution machinery. Subclasses add their own fields and validation.
    """

    audiocpp_uri: str = DEFAULT_AUDIOCPP_URI
    """Base URI of the audio.cpp HTTP server, e.g. ``http://localhost:8080``."""

    enable_zeroconf: bool = False
    """Whether to register mDNS ``_wyoming._tcp.local.`` discovery."""

    def endpoint(self, path: str) -> str:
        """Join the base URI and an endpoint path into a full URL.

        The trailing slash on the base URI is stripped so the join never
        produces a double slash.
        """
        uri = self.audiocpp_uri.rstrip("/")
        return f"{uri}/{path.lstrip('/')}"

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "BridgeConfig":
        """Build config from a dict, setting only keys present in ``data``."""
        result = cls()
        for field in fields(cls):
            if field.name in data:
                setattr(result, field.name, data[field.name])
        return result

    def _apply(self, overrides: Dict[str, Any]) -> "BridgeConfig":
        """Return a copy of ``self`` with ``overrides`` applied.

        Existing values (e.g. loaded from ``config.json``) are preserved; only
        the keys present in ``overrides`` are changed.
        """
        result = self
        for key, value in overrides.items():
            if key in self.__dataclass_fields__:
                setattr(result, key, value)
        return result

    def _apply_env(self) -> "BridgeConfig":
        """Return a copy of ``self`` with ``WYO_<FIELD>`` env vars applied.

        Only scalar types are parsed; non-primitive fields (e.g.
        ``List[VoiceConfig]``) are skipped and must come from config.json.
        """
        result = self
        for field in fields(type(self)):
            value = os.environ.get(ENV_PREFIX + field.name.upper())
            if value is None or value == "":
                continue
            if field.type not in _SCALAR_TYPES:
                continue
            result = dataclasses.replace(
                result, **{field.name: _parse_env(field.type, value)}
            )
        return result

    @classmethod
    def from_args(
        cls,
        config_path: Optional[Path] = None,
        **overrides: Any,
    ) -> "BridgeConfig":
        """Build config: ``config.json``, then ``WYO_*`` env vars, then CLI.

        ``None`` override values are ignored, so a missing flag keeps the
        environment/config.json value (which itself defaults if absent).
        """
        data: Dict[str, Any] = {}
        path = Path(config_path) if config_path is not None else None
        if path and path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except ValueError as exc:
                raise ValueError(f"{path}: {exc}") from exc
        config = cls.from_dict(data)
        config = config._apply_env()
        config = config._apply(
            {key: value for key, value in overrides.items() if value is not None}
        )
        config.validate()
        return config

    def validate(self) -> None:
        """Validate shared fields. Subclasses override and call ``super()``."""
        if not self.audiocpp_uri:
            raise ValueError("audiocpp_uri must be set")
        scheme, _, _ = self.audiocpp_uri.partition("://")
        if scheme not in ("http", "https"):
            raise ValueError(
                f"audiocpp_uri scheme must be http or https: {self.audiocpp_uri}"
            )
