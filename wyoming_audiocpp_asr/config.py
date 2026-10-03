"""Configuration for the Wyoming audio.cpp ASR bridge.

Configuration is layered, later layers win:

1. Defaults (the dataclass field defaults).
2. ``config.json`` with defaults and project settings.
3. Environment variables ``WYO_<FIELD>`` (the field name, upper-cased), so the
   service can be configured from a container's environment without flags.
4. Command-line flags.

audio.cpp is reached through its OpenAI-compatible transcription endpoint. The
bridge speaks the Wyoming event protocol over TCP (``AsyncTcpServer``) and
relays the result to the client.
"""

from __future__ import annotations

import dataclasses
import os
from dataclasses import dataclass, fields
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

DEFAULT_CONFIG_PATH = Path("config.json")
DEFAULT_AUDIOCPP_URI = "http://localhost:8080"
DEFAULT_MODEL = "hviske"
DEFAULT_LANGUAGE = "da"
DEFAULT_URI = "tcp://0.0.0.0:55001"
DEFAULT_WEB_SERVER_HOST = "127.0.0.1"
DEFAULT_WEB_SERVER_PORT = 5000
ENV_PREFIX = "WYO_"

# Fields audio.cpp accepts on the transcription endpoint.
_AUDIOCPP_ENDPOINT = "/v1/audio/transcriptions"

_BOOL_TRUE = {"1", "true", "yes", "on"}
_BOOL_FALSE = {"0", "false", "no", "off"}


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
    """Parse an environment string into the type of a ``Config`` field."""
    if type_str in ("bool", "Optional[bool]"):
        return _parse_bool(value)
    if type_str in ("int", "Optional[int]"):
        return _parse_int(value)
    if "List[" in type_str:
        return [item.strip() for item in value.split(",") if item.strip()]
    return value


@dataclass
class Config:
    """Resolved configuration for the Wyoming ASR bridge.

    Every value is final here; command-line overrides have already been merged.
    """

    audiocpp_uri: str = DEFAULT_AUDIOCPP_URI
    """Base URI of the audio.cpp HTTP server, e.g. ``http://localhost:8080``.

    The Wyoming service talks to ``<audiocpp_uri>/v1/audio/transcriptions``.
    """

    asr_model: str = DEFAULT_MODEL
    """audio.cpp model id used for transcription. Defaults to ``hviske``."""

    asr_language: Optional[str] = DEFAULT_LANGUAGE
    """Language hint passed to audio.cpp. ``None`` disables it."""

    uri: str = DEFAULT_URI
    """Wyoming TCP bind URI, e.g. ``tcp://0.0.0.0:55001``."""

    enable_zeroconf: bool = False
    """Whether to register mDNS ``_wyoming._tcp.local.`` discovery."""

    asr_web_server: bool = False
    """Whether to also start the demo browser web server (requires the
    ``web`` optional dependencies)."""

    asr_web_server_host: str = DEFAULT_WEB_SERVER_HOST
    """Interface for the demo web server."""

    asr_web_server_port: int = DEFAULT_WEB_SERVER_PORT
    """Port for the demo web server."""

    asr_web_server_allow: Optional[List[str]] = None
    """Optional allow-list of IP addresses/CIDRs for the demo web server.
    When set, the demo web server binds all interfaces and serves only these
    peer addresses (the UI has no authentication)."""

    @property
    def transcription_endpoint(self) -> str:
        """Full transcription endpoint URL.

        ``_AUDIOCPP_ENDPOINT`` is a slash-less path prefix, so the base URI and
        the endpoint are joined with exactly one ``/``.
        """
        uri = self.audiocpp_uri.rstrip("/")
        return f"{uri}/{_AUDIOCPP_ENDPOINT.lstrip('/')}"

    def parse_tcp_uri(self) -> tuple[str, int]:
        """Parse ``uri`` into ``(host, port)``.

        Raises ``ValueError`` when it is not a ``tcp://host:port`` URI.
        """
        parsed = urlparse(self.uri)
        if parsed.scheme != "tcp" or not parsed.hostname or not parsed.port:
            raise ValueError(f"uri must be tcp://host:port: {self.uri}")
        return parsed.hostname, parsed.port

    def to_dict(self) -> Dict[str, Any]:
        return {
            "audiocpp_uri": self.audiocpp_uri,
            "asr_model": self.asr_model,
            "asr_language": self.asr_language,
            "uri": self.uri,
            "enable_zeroconf": self.enable_zeroconf,
            "asr_web_server": self.asr_web_server,
            "asr_web_server_host": self.asr_web_server_host,
            "asr_web_server_port": self.asr_web_server_port,
            "asr_web_server_allow": self.asr_web_server_allow,
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

        Existing values (e.g. loaded from ``config.json``) are preserved; only
        the keys present in ``overrides`` are changed. The starting point is
        ``self``, not the defaults, so ``from_args`` keeps the file-loaded
        values unless a higher layer supplies them.
        """
        result = self
        for key, value in overrides.items():
            if key in self.__dataclass_fields__:
                setattr(result, key, value)
        return result

    def _apply_env(self) -> "Config":
        """Return a copy of ``self`` with ``WYO_<FIELD>`` env vars applied."""
        result = self
        for field in fields(type(self)):
            value = os.environ.get(ENV_PREFIX + field.name.upper())
            if value is None or value == "":
                continue
            result = dataclasses.replace(
                result, **{field.name: _parse_env(field.type, value)}
            )
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

        self.parse_tcp_uri()

        if self.asr_web_server and not self.asr_web_server_port > 0:
            raise ValueError(
                f"asr_web_server_port must be > 0 when asr_web_server is enabled: "
                f"{self.asr_web_server_port}"
            )

    @classmethod
    def from_args(
        cls,
        config_path: Optional[Path] = None,
        **overrides: Any,
    ) -> "Config":
        """Build config: ``config.json``, then ``WYO_*`` env vars, then CLI.

        ``None`` override values are ignored, so a missing flag keeps the
        environment/config.json value (which itself defaults if absent).
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
        config = config._apply_env()
        config = config._apply(
            {key: value for key, value in overrides.items() if value is not None}
        )
        config.validate()
        return config
