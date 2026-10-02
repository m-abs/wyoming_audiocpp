"""Turn Wyoming TTS events into calls to audio.cpp's TTS endpoint.

audio.cpp is an OpenAI-compatible HTTP server, not a Wyoming service, so this
bridge relays the raw bytes and turns them back into TTS chunks on the edge
(streaming). Reuses audiocpp_client.synthesize() and Config; only here do
events map onto those calls.

Streaming: emit ``AudioStart`` with the canonical format, then relay each
audio.cpp batch as an ``AudioChunk`` carrying raw PCM bytes. The synthesized
audio is also written to a WAV file on disk; the stream terminates with
``AudioStop``.
"""


from dataclasses import dataclass
import asyncio
import os
import tempfile
import wave
from typing import TYPE_CHECKING, List, Optional

from . import __version__
from . import audiocpp_client

from wyoming.info import (
    Attribution,
    Describe,
    Info,
    TtsProgram,
    TtsVoice,
    TtsVoiceSpeaker,
)
from wyoming.server import AsyncEventHandler
from wyoming.audio import AudioChunk, AudioStart, AudioStop
from wyoming.tts import Synthesize

DEFAULT_SAMPLE_RATE = 16000
WIDTH_BYTES = 2
CHANNELS = 1


if TYPE_CHECKING:
    from .config import Config


@dataclass
class Voice:
    """Minimal voice description for the service info message."""

    name: str
    description: str
    format: str
    languages: List[str]


class AudioCppTtsEventHandler(AsyncEventHandler):
    """Wyoming TTS event handler that bridges to audio.cpp."""

    def __init__(self, reader, writer, config: "Config", wav_path: Optional[str] = None) -> None:
        super().__init__(reader, writer)
        self.config = config
        self._wav_path = wav_path or os.path.join(tempfile.gettempdir(), "audio.cpp-tts.wav")
        self._wav: Optional["wave.Wave_write"] = None

    async def handle_event(self, event) -> bool:
        """Handle an event; return True to stay connected, False to disconnect."""
        if Describe.is_type(event.type):
            await self._handle_describe(event)
            return True

        if Synthesize.is_type(event.type):
            await self._handle_synthesize(event)
            return True

        return True

    async def _handle_describe(self, event) -> None:
        """Send the service info in response to a Describe event."""
        tts_info = Info(
                        tts=[
                            TtsProgram(
                                attribution=Attribution(
                                    name="audio.cpp",
                                    url="https://github.com/mudam/audiocpp",
                                ),
                                name="Wyoming Audio.cpp - tts",
                                installed=True,
                                description="audio.cpp text-to-speech",
                                version=__version__,
                                voices=self._build_tts_info(self.config.tts_voice),
                                supports_synthesize_streaming=True,
                            )
                        ]
                    )
        await self.write_event(tts_info.event())

    def _build_tts_info(self, voice) -> List[TtsVoice]:
        """Build the Wyoming TTS voices for the service info message."""
        if voice is None:
            return []
        return [
            TtsVoice(
                name=voice.name or "default",
                description=voice.name or "audio.cpp voice",
                languages=[voice.language] if voice.language else ["en"],
                attribution=Attribution(
                    name="audio.cpp",
                    url="https://github.com/mudam/audiocpp",
                ),
                installed=True,
                version=None,
                speakers=[TtsVoiceSpeaker(
                    name=voice.name or "default",
                ),]
            )
        ]

    def _open_wav(self) -> None:
        """Open the WAV sink for the current synthesis."""
        self._wav = wave.open(self._wav_path, "wb")
        self._wav.setnchannels(CHANNELS)
        self._wav.setsampwidth(WIDTH_BYTES)
        self._wav.setframerate(DEFAULT_SAMPLE_RATE)

    def _close_wav(self) -> None:
        if self._wav is not None:
            self._wav.close()
            self._wav = None

    async def _handle_synthesize(self, event) -> None:
        """Start a synthesize request and stream audio.cpp output to the WAV.

        The terminating ``AudioStop`` event and the WAV close run in a
        ``finally`` so the client's stream is always terminated and the file
        handle released, even if the upstream audio.cpp call fails mid-stream.
        """
        synthesize = Synthesize.from_event(event)
        self._open_wav()
        await self.write_event(
            AudioStart(
                rate=DEFAULT_SAMPLE_RATE,
                width=WIDTH_BYTES,
                channels=CHANNELS,
            ).event()
        )

        try:
            async for audio in self._synthesize(synthesize):
                if self._wav is not None:
                    self._wav.writeframes(audio)
                await self.write_event(
                    AudioChunk(
                        audio=audio,
                        rate=DEFAULT_SAMPLE_RATE,
                        width=WIDTH_BYTES,
                        channels=CHANNELS,
                    ).event()
                )
        finally:
            self._close_wav()
            await self.write_event(AudioStop().event())

    async def _synthesize(self, synthesize):
        """Yield audio.cpp audio chunks for the synthesize request.

        audio.cpp streams its response in batches; each batch is written to the
        WAV and relayed as an empty-text ``SynthesizeChunk``. The blocking HTTP
        call runs in a thread so it does not stall the Wyoming event loop.
        """
        text = synthesize.text
        chunks = await self._run_blocking(
            audiocpp_client.synthesize,
            self.config.tts_endpoint,
            self.config.tts_voice,
            text,
        )
        for chunk in chunks:
            yield chunk

    @staticmethod
    def _run_blocking(func, *args, **kwargs):
        """Run a blocking generator in a thread pool and return its chunks."""
        loop = asyncio.get_running_loop()
        return loop.run_in_executor(None, lambda: list(func(*args, **kwargs)))
