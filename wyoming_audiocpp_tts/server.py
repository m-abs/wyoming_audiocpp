"""Wyoming TCP server for the audio.cpp TTS bridge.

This is the default entry point. It binds a Wyoming ``AsyncTcpServer`` and serves
TTS over the Wyoming event protocol. audio.cpp itself is an OpenAI-compatible
HTTP server, not a Wyoming service, so this bridge relays the raw audio bytes
and turns them back into TTS chunks on the edge (see tts_handler.py).

The Flask HTTP server (tts_server.py) is kept verbatim and is only used by the
optional demo web server; importing it here would couple the Wyoming service to
the optional ``web`` dependencies, so it is deliberately not imported.
"""

from __future__ import annotations

import asyncio
import logging
from functools import partial
from typing import TYPE_CHECKING

from wyoming.server import AsyncServer, AsyncTcpServer

logger = logging.getLogger("wyoming_audiocpp_tts")

TTS_SERVICE_NAME = "wyoming-audiocpp-tts"


if TYPE_CHECKING:
    from .config import TtsConfig
    from .tts_handler import AudioCppTtsEventHandler
def create_handler(reader, writer, config: "TtsConfig") -> "AudioCppTtsEventHandler":
    """Wyoming handler factory for ``AsyncServer.run`` / ``AsyncServer.start``."""
    from .tts_handler import AudioCppTtsEventHandler

    return AudioCppTtsEventHandler(reader, writer, config)
def handler_factory(config: "TtsConfig"):
    """Bind ``config`` into the ``(reader, writer) -> handler`` factory."""
    return partial(create_handler, config=config)


async def _run(server: AsyncTcpServer, config: "TtsConfig") -> None:
    """Serve TTS until stopped, registering mDNS discovery when enabled.

    ``AsyncServer.run`` owns the event loop, so the zeroconf task is created
    inside it rather than before the loop starts.
    """
    if config.enable_zeroconf:
        from wyoming.zeroconf import HomeAssistantZeroconf

        hass_zeroconf = HomeAssistantZeroconf(
            name=TTS_SERVICE_NAME,
            port=server.port,
            host=server.host,
        )
        asyncio.create_task(hass_zeroconf.register_server())

    await server.run(handler_factory(config))


def create_tcp_server(config: "TtsConfig") -> None:
    """Run the Wyoming TCP server (blocking; starts the asyncio loop)."""
    server = AsyncServer.from_uri(config.tts_uri)
    asyncio.run(_run(server, config))
