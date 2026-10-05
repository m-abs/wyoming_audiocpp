"""Configuration for the Wyoming audio.cpp ASR bridge.

Subclasses ``BridgeConfig`` from ``wyoming_audiocpp_common`` with ASR-specific
fields: model, language, bind URI, and demo web server settings.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Union
from urllib.parse import urlparse

from wyoming_audiocpp_common.config import BridgeConfig

DEFAULT_MODEL = "hviske"
DEFAULT_LANGUAGE = "da"
DEFAULT_URI = "tcp://0.0.0.0:11301"
DEFAULT_WEB_SERVER_HOST = "127.0.0.1"
DEFAULT_WEB_SERVER_PORT = 5000

# Fields audio.cpp accepts on the transcription endpoint.
_AUDIOCPP_ENDPOINT = "/v1/audio/transcriptions"


@dataclass
class AsrConfig(BridgeConfig):
    """Resolved configuration for the Wyoming ASR bridge.

    Every value is final here; command-line overrides have already been merged.
    """

    asr_model: str = DEFAULT_MODEL
    """audio.cpp model id used for transcription. Defaults to ``hviske``."""

    asr_language: Union[str, List[str]] = DEFAULT_LANGUAGE
    """Language hint passed to audio.cpp. A single string (e.g. ``"da"``) or a
    list of supported language codes (e.g. ``["da", "en"]``). ``None`` disables
    the hint."""

    asr_uri: str = DEFAULT_URI
    """Wyoming TCP bind URI, e.g. ``tcp://0.0.0.0:11301``."""

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
        """Full transcription endpoint URL."""
        return self.endpoint(_AUDIOCPP_ENDPOINT)

    def parse_tcp_uri(self) -> tuple[str, int]:
        """Parse ``asr_uri`` into ``(host, port)``.

        Raises ``ValueError`` when it is not a ``tcp://host:port`` URI.
        """
        parsed = urlparse(self.asr_uri)
        if parsed.scheme != "tcp" or not parsed.hostname or not parsed.port:
            raise ValueError(f"asr_uri must be tcp://host:port: {self.asr_uri}")
        return parsed.hostname, parsed.port

    def validate(self) -> None:
        super().validate()
        if not self.asr_model:
            raise ValueError("asr_model must be set")
        self.parse_tcp_uri()
        if self.asr_language is not None:
            if not isinstance(self.asr_language, (str, list)):
                raise ValueError(
                    f"asr_language must be a string or a list of strings, "
                    f"got {type(self.asr_language).__name__}"
                )
            if isinstance(self.asr_language, list):
                for lang in self.asr_language:
                    if not isinstance(lang, str):
                        raise ValueError(
                            f"asr_language list items must be strings, "
                            f"got {type(lang).__name__}"
                        )

        if self.asr_web_server and not self.asr_web_server_port > 0:
            raise ValueError(
                f"asr_web_server_port must be > 0 when asr_web_server is enabled: "
                f"{self.asr_web_server_port}"
            )
