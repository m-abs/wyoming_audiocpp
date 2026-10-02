"""Turn Wyoming TTS events into calls to audio.cpp's TTS endpoint.

audio.cpp is an OpenAI-compatible HTTP server, not a Wyoming service, so this
bridge relays the raw bytes and turns them back into TTS chunks on the edge
(streaming). Reuses audiocpp_client.synthesize() and Config; only here do
events map onto those calls.

Streaming: emit an empty text chunk on ``SynthesizeStart``, then real chunks
with progress after each audio.cpp batch. The synthesized audio is written to a
WAV file on disk; Wyoming's ``SynthesizeChunk`` carries only empty ``text``
placeholders while the audio bytes stream through.
"""


from dataclasses import dataclass
import asyncio
import logging
import os
import tempfile
import wave
from typing import TYPE_CHECKING, List, Optional

from . import audiocpp_client
from wyoming.info import (
    Attribution,
    Describe,
    Info,
    TtsProgram,
    TtsVoice,
)
from wyoming.server import AsyncEventHandler
from wyoming.tts import (
    Synthesize,
    SynthesizeChunk,
    SynthesizeStart,
    SynthesizeStop,
    SynthesizeStopped,
)

logger = logging.getLogger("wyoming_audiocpp_tts")

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

        if SynthesizeStart.is_type(event.type):
            await self._handle_synthesize_start(event)
            return True

        if SynthesizeChunk.is_type(event.type):
            await self._handle_synthesize_chunk(event)
            return True

        if SynthesizeStop.is_type(event.type):
            await self._handle_synthesize_stop(event)
            return True

        if SynthesizeStopped.is_type(event.type):
            await self._handle_synthesize_stopped(event)
            return False

        return True

    async def _handle_describe(self, event) -> None:
        """Send the service info in response to a Describe event."""
        await self.write_event(
            Info(
                tts=[
                    TtsProgram(
                        attribution=Attribution(
                            name="audio.cpp",
                            url="https://github.com/mudam/audiocpp",
                        ),
                        name="audio.cpp",
                        installed=True,
                        description="audio.cpp text-to-speech",
                        version=None,
                        voices=self._build_tts_info(self.config.tts_voice),
                        supports_synthesize_streaming=True,
                    )
                ]
            ).event(),
        )

    def _build_tts_info(self, voice) -> List[TtsVoice]:
        """Build the Wyoming TTS voices for the service info message."""
        if voice is None:
            return []
        return [
            TtsVoice(
                name=voice.name or "default",
                description=voice.name or "audio.cpp voice",
                languages=voice.language or ["en"],
                attribution={"name": "audio.cpp", "url": "https://github.com/mudam/audiocpp"},
                installed=True,
                version=None,
                speakers=None,
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
        """Start a synthesize request and stream audio.cpp output to the WAV."""
        from wyoming.tts import Synthesize as _Synthesize

        synthesize = _Synthesize.from_event(event)
        self._open_wav()
        await self.write_event(SynthesizeStart().event())
        async for audio in self._synthesize(synthesize):
            if self._wav is not None:
                self._wav.writeframes(audio)
            await self.write_event(SynthesizeChunk(text="").event())

        await self.write_event(SynthesizeStop().event())
        self._close_wav()

    async def _handle_synthesize_chunk(self, event) -> None:
        """Emit an empty text chunk in response to an incoming chunk event."""
        await self.write_event(SynthesizeChunk(text="").event())

    async def _handle_synthesize_start(self, event) -> None:
        """Client-driven start: close any open WAV and end the stream."""
        self._close_wav()
        await self.write_event(SynthesizeStop().event())

    async def _handle_synthesize_stopped(self, event) -> None:
        """Client-driven stop: close the WAV and disconnect."""
        self._close_wav()

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

    def _request_body(self, text: str) -> Dict[str, Any]:
        """Build the audio.cpp request body, merging config voice with the text."""
        from .config import VoiceConfig

        voice = self.config.tts_voice
        if voice is None:
            return {"model": DEFAULT_VOICE_MODEL, "input": text}
        return voice.request_body(text)


