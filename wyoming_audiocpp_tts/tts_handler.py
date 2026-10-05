"""Turn Wyoming TTS events into calls to audio.cpp's TTS endpoint.

audio.cpp's speech endpoint returns a WAV file; this bridge parses the header
to get the real format, strips it, and relays raw PCM bytes to Wyoming clients.
The synthesized audio is also written to a WAV file on disk; the stream
terminates with ``AudioStop``.
"""


from dataclasses import dataclass
import asyncio
import logging
import os
import tempfile
import time
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
from wyoming.tts import Synthesize, SynthesizeChunk, SynthesizeStart, SynthesizeStop, SynthesizeStopped

if TYPE_CHECKING:
    from .config import TtsConfig

_LOGGER = logging.getLogger(__name__)

@dataclass
class Voice:
    """Minimal voice description for the service info message."""

    name: str
    description: str
    format: str
    languages: List[str]


class AudioCppTtsEventHandler(AsyncEventHandler):
    """Wyoming TTS event handler that bridges to audio.cpp."""

    def __init__(self, reader, writer, config: "TtsConfig", wav_path: Optional[str] = None) -> None:
        super().__init__(reader, writer)
        self.config = config
        self._wav_path = wav_path or os.path.join(tempfile.gettempdir(), "audio.cpp-tts.wav")
        self._wav: Optional["wave.Wave_write"] = None

    async def handle_event(self, event) -> bool:
        """Handle an event; return True to stay connected, False to disconnect."""
        _LOGGER.debug("Event: %s", event.type)
        if Describe.is_type(event.type):
            await self._handle_describe(event)
            return True

        if Synthesize.is_type(event.type):
            await self._handle_synthesize(event)
            return True

        if SynthesizeStop.is_type(event.type):
            # HA signals end of input; acknowledge with SynthesizeStopped.
            _LOGGER.debug("SynthesizeStop -> SynthesizeStopped")
            await self.write_event(SynthesizeStopped().event())
            return True

        if SynthesizeStart.is_type(event.type) or SynthesizeChunk.is_type(event.type):
            # HA sends these as part of its TTS handshake; the actual synthesis
            # uses the non-streaming Synthesize event. Acknowledge and stay.
            _LOGGER.debug("Ignoring %s", event.type)
            return True

        _LOGGER.error("Unhandled event type: %s", event.type)

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
                                voices=self._build_tts_info(self.config.tts_voices),
                                supports_synthesize_streaming=True,
                            )
                        ]
                    )
        await self.write_event(tts_info.event())

    def _build_tts_info(self, voices: List["VoiceConfig"]) -> List[TtsVoice]:
        """Build the Wyoming TTS voices for the service info message."""
        return [
            TtsVoice(
                name=v.voice_name,
                description=f"{v.voice_name} ({v.model})",
                languages=[v.language] if v.language else ["en"],
                attribution=Attribution(
                    name="audio.cpp",
                    url="https://github.com/0xShug0/audio.cpp",
                ),
                installed=True,
                version=None,
                speakers=[TtsVoiceSpeaker(name=v.voice_name)],
            )
            for v in voices
        ]

    def _find_voice(self, name: Optional[str]) -> "VoiceConfig":
        """Select a voice by name; fall back to the first voice."""
        if name:
            for v in self.config.tts_voices:
                if v.voice_name == name:
                    return v
            _LOGGER.warning("Voice %r not found; falling back to first voice", name)
        return self.config.tts_voices[0]

    def _open_wav(self, fmt: "audiocpp_client.WavFormat") -> None:
        """Open the WAV sink for the current synthesis."""
        self._wav = wave.open(self._wav_path, "wb")
        self._wav.setnchannels(fmt.channels)
        self._wav.setsampwidth(fmt.sampwidth)
        self._wav.setframerate(fmt.sample_rate)

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
        _LOGGER.debug("Synthesize: %r", synthesize.text[:80])

        t0 = time.perf_counter()
        try:
            fmt, chunks = await self._synthesize(synthesize)
        except Exception:
            # Upstream failed; close the stream.
            _LOGGER.exception("Synthesis failed")
            await self.write_event(AudioStop().event())
            return
        elapsed = time.perf_counter() - t0

        total_pcm = sum(len(c) for c in chunks)
        audio_duration = total_pcm / (fmt.sample_rate * fmt.sampwidth * fmt.channels)
        ratio = audio_duration / elapsed if elapsed > 0 else float("inf")
        _LOGGER.debug(
            "Generated %.1fs audio in %.2fs (%.1fx realtime)",
            audio_duration,
            elapsed,
            ratio,
        )

        self._open_wav(fmt)
        await self.write_event(
            AudioStart(
                rate=fmt.sample_rate,
                width=fmt.sampwidth,
                channels=fmt.channels,
            ).event()
        )
        try:
            for audio in chunks:
                if self._wav is not None:
                    self._wav.writeframes(audio)
                await self.write_event(
                    AudioChunk(
                        audio=audio,
                        rate=fmt.sample_rate,
                        width=fmt.sampwidth,
                        channels=fmt.channels,
                    ).event()
                )
        finally:
            self._close_wav()
            await self.write_event(AudioStop().event())

    async def _synthesize(
        self, synthesize
    ) -> tuple["audiocpp_client.WavFormat", List[bytes]]:
        """Call audio.cpp in a thread and return the format + all PCM chunks.

        The blocking HTTP call runs in a thread so it does not stall the
        Wyoming event loop. Chunks are buffered so they arrive in order.
        """
        text = synthesize.text
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None,
            lambda: audiocpp_client.synthesize(
                self.config.tts_endpoint,
                self._find_voice(
                    synthesize.voice.name if synthesize.voice else None
                ),
                text,
            ),
        )
