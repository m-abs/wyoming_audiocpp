"""Wyoming TCP server for the audio.cpp ASR bridge.

The service is a standard Wyoming service: an ``AsyncTcpServer`` on
``config.uri`` (``tcp://host:port``), with opt-in mDNS discovery via
``wyoming.zeroconf.HomeAssistantZeroconf`` so Home Assistant's Wyoming
integration can find it over ``_wyoming._tcp.local.``.

The Flask demo server (``asr_server.py``) is not part of this module and is
only reachable through ``--web-server`` (see ``web_server.py``).
"""

from __future__ import annotations

import asyncio
import logging
from functools import partial

from wyoming.server import AsyncServer, AsyncTcpServer

from .asr_handler import AudioCppAsrEventHandler
from .config import Config

logger = logging.getLogger("wyoming_audiocpp_asr")

ASR_SERVICE_NAME = "wyoming-audiocpp-asr"


def create_handler(reader, writer, config: Config) -> AudioCppAsrEventHandler:
    """Wyoming handler factory for ``AsyncServer.run`` / ``AsyncServer.start``."""
    return AudioCppAsrEventHandler(reader, writer, config)


def handler_factory(config: Config):
    """Bind ``config`` into the ``(reader, writer) -> handler`` factory."""
    return partial(create_handler, config=config)


def zeroconf_name(config: Config) -> str:
    """mDNS service name: URI host if set, else default."""
    host, _ = config.parse_tcp_uri()
    return host if host and host != "0.0.0.0" else ASR_SERVICE_NAME


async def _register_zeroconf(server: AsyncTcpServer, config: Config) -> None:
    """Register mDNS discovery for ``server`` inside the event loop.

    Awaiting ``register_server()`` before serving is deterministic: if the
    registration fails, startup aborts before the port is announced as ready.
    ``host=None`` lets ``HomeAssistantZeroconf`` detect the interface address
    itself, which matters when the bind address is ``0.0.0.0``.
    """
    from wyoming.zeroconf import HomeAssistantZeroconf

    host = server.host if server.host and server.host != "0.0.0.0" else None
    hass_zeroconf = HomeAssistantZeroconf(
        name=zeroconf_name(config), port=server.port, host=host
    )
    await hass_zeroconf.register_server()
    logger.debug("Zeroconf discovery enabled")


async def _run(server: AsyncTcpServer, config: Config) -> None:
    if config.enable_zeroconf:
        await _register_zeroconf(server, config)
    await server.run(handler_factory(config))


def create_tcp_server(config: Config) -> None:
    """Run the Wyoming TCP server (blocking; starts the asyncio loop)."""
    server = AsyncServer.from_uri(config.asr_uri)
    if config.enable_zeroconf and not isinstance(server, AsyncTcpServer):
        raise ValueError("Zeroconf requires tcp:// uri")
    asyncio.run(_run(server, config))
