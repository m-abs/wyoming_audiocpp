"""End-to-end test: the TTS bridge emits a Wyoming audio stream a real client can read.

The handler unit tests mock ``write_event`` and so never verify the on-the-wire
framing. This drives the actual ``AudioCppTtsEventHandler`` through a real
``AsyncTcpServer`` with a real ``wyoming.client.AsyncTcpClient`` (upstream
audio.cpp mocked) and asserts the client receives ``AudioStart`` ->
``AudioChunk``+ -> ``AudioStop`` carrying the raw PCM bytes. This is the exact
sequence Home Assistant's Wyoming TTS integration requires; emitting any other
event family (e.g. the client-side streaming-text events) leaves the client
without audio and makes it time out.
"""

import asyncio

from unittest import mock

import pytest
from wyoming.audio import AudioChunk, AudioStart, AudioStop
from wyoming.client import AsyncTcpClient
from wyoming.server import AsyncTcpServer
from wyoming.tts import Synthesize

from ..config import TtsConfig
from ..server import handler_factory
from .. import audiocpp_client


@pytest.fixture
async def server_and_port():
    """Run the bridge on an ephemeral port; yield (server, port) and tear down."""
    config = TtsConfig()
    server = AsyncTcpServer("127.0.0.1", 0)
    await server.start(handler_factory(config))
    port = server._server.sockets[0].getsockname()[1]
    yield server, port
    await server.stop()
    server._server.close()


def fake_synthesize(endpoint, voice, text, **kwargs):
    from wyoming_audiocpp_tts.audiocpp_client import WavFormat
    fmt = WavFormat(sample_rate=24000, channels=1, sampwidth=2)
    return fmt, [b"\x01\x02\x03\x04", b"\x05\x06\x07\x08"]


async def test_client_receives_audio_stream(server_and_port):
    server, port = server_and_port

    with mock.patch.object(audiocpp_client, "synthesize", side_effect=fake_synthesize):
        async with AsyncTcpClient("127.0.0.1", port) as client:
            await client.write_event(Synthesize(text="hello").event())

            types = []
            payloads = []
            while True:
                event = await client.read_event()
                if AudioStart.is_type(event.type):
                    assert event.data["rate"] == 24000
                    assert event.data["width"] == 2
                    assert event.data["channels"] == 1
                    types.append("audio-start")
                elif AudioChunk.is_type(event.type):
                    types.append("audio-chunk")
                    payloads.append(event.payload)
                elif AudioStop.is_type(event.type):
                    types.append("audio-stop")
                    break
                else:
                    pytest.fail(f"unexpected event on the wire: {event.type}")

    assert types == ["audio-start", "audio-chunk", "audio-chunk", "audio-stop"]
    assert b"".join(payloads) == b"\x01\x02\x03\x04\x05\x06\x07\x08"
