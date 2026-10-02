"""Turn Wyoming ASR events into calls to audio.cpp's transcription endpoint.

audio.cpp is an OpenAI-compatible HTTP server, not a Wyoming service, so this
bridge speaks the Wyoming event protocol (``wyoming.server.AsyncEventHandler``
over ``AsyncTcpServer``) and relays the raw audio to audio.cpp. The audio is
accumulated in an in-memory 16-bit/16 kHz mono WAV; on the ``AudioStop`` edge
the WAV is transcribed non-streamingly and one ``Transcript`` event is sent
before the connection is closed (one response per request, like
``wyoming-faster-whisper``'s ``DispatchEventHandler``).

Language precedence: an explicit ``Transcribe`` language wins; otherwise the
``config.language`` hint is sent. A client ``"auto"`` (or ``None``) keeps the
hint disabled and lets audio.cpp auto-detect.
"""

from __future__ import annotations

import asyncio
import io
import logging
import wave
from typing import TYPE_CHECKING, Optional

from wyoming.asr import Transcribe, Transcript
from wyoming.audio import AudioChunk, AudioChunkConverter, AudioStart, AudioStop
from wyoming.error import Error
from wyoming.event import Event
from wyoming.info import AsrModel, AsrProgram, Attribution, Describe, Info
from wyoming.server import AsyncEventHandler

from . import __version__

if TYPE_CHECKING:
    from .config import Config

logger = logging.getLogger("wyoming_audiocpp_asr")

SAMPLE_RATE = 16000
SAMPLE_WIDTH = 2
CHANNELS = 1

# audio.cpp treats the hint as an explicit language; "auto" means no hint.
_AUTO_LANGUAGE = "auto"


class AudioCppAsrEventHandler(AsyncEventHandler):
    """Wyoming ASR event handler that bridges to audio.cpp.

    Dispatches on the Wyoming ASR event stream:

    * ``Transcribe``  -- remember the language for the upcoming utterance.
    * ``AudioStart``  -- open an in-memory WAV for the utterance.
    * ``AudioChunk``  -- convert to 16-bit/16 kHz mono and append the audio.
    * ``AudioStop``   -- transcribe the WAV, send one ``Transcript``, and
      disconnect (``False``).
    * ``Describe``    -- reply with the service ``Info``.
    """

    def __init__(self, reader, writer, config: "Config") -> None:
        super().__init__(reader, writer)
        self.config = config
        self._language: Optional[str] = None
        self._wav: Optional[wave.Wave_write] = None
        self._wav_buffer: Optional[io.BytesIO] = None
        self._converter = AudioChunkConverter(
            rate=SAMPLE_RATE, width=SAMPLE_WIDTH, channels=CHANNELS
        )

    async def handle_event(self, event: Event) -> bool:
        if Transcribe.is_type(event.type):
            self._language = Transcribe.from_event(event).language
            return True

        if AudioStart.is_type(event.type):
            self._start_utterance()
            return True

        if AudioChunk.is_type(event.type):
            self._append_audio(AudioChunk.from_event(event))
            return True

        if AudioStop.is_type(event.type):
            await self._finish_utterance()
            return False

        if Describe.is_type(event.type):
            await self.write_event(build_asr_info(self.config).event())
            return True

        return True

    def _start_utterance(self) -> None:
        """Open the in-memory WAV for a new utterance."""
        self._wav_buffer = io.BytesIO()
        self._wav = wave.open(self._wav_buffer, "wb")
        self._wav.setnchannels(CHANNELS)
        self._wav.setsampwidth(SAMPLE_WIDTH)
        self._wav.setframerate(SAMPLE_RATE)

    def _append_audio(self, chunk: AudioChunk) -> None:
        """Convert one chunk to the canonical format and append it to the WAV."""
        if self._wav is None:
            logger.warning("AudioChunk before AudioStart; ignoring")
            return
        converted = self._converter.convert(chunk)
        self._wav.writeframes(converted.audio)

    def _close_wav(self) -> bytes:
        """Close the in-memory WAV and return its bytes (empty if no audio)."""
        if self._wav is None:
            return b""
        self._wav.close()
        self._wav = None
        assert self._wav_buffer is not None
        wav_bytes = self._wav_buffer.getvalue()
        self._wav_buffer = None
        return wav_bytes

    async def _finish_utterance(self) -> None:
        """Transcribe the accumulated WAV and send the final Transcript.

        ``audio.cpp`` failures are surfaced to the Wyoming client as an
        ``Error`` event; the utterance is still closed afterwards. The blocking
        HTTP call runs in a thread so it does not stall other clients, and the
        response write is awaited directly so the client receives it before the
        connection closes.
        """
        from . import audiocpp_client

        wav_bytes = self._close_wav()

        language = self._language
        if not language or language == _AUTO_LANGUAGE:
            language = self.config.language

        try:
            if not wav_bytes:
                # No audio was accumulated: nothing to transcribe.
                result: dict = {"text": "", "language": language}
            else:
                result = await asyncio.to_thread(
                    audiocpp_client.transcribe,
                    self.config.transcription_endpoint,
                    wav_bytes,
                    self.config.model,
                    language,
                )
        except Exception as exc:  # noqa: BLE001 -- relay to the Wyoming client
            logger.exception("audio.cpp transcription failed")
            await self.write_event(
                Error(text=f"audio.cpp transcription failed: {exc}").event()
            )
            return

        transcript = Transcript(
            text=result.get("text", ""), language=result.get("language")
        )
        await self.write_event(transcript.event())

    async def disconnect(self) -> None:
        """Release the WAV buffer when the client goes away mid-utterance."""
        self._close_wav()


def build_asr_info(config: "Config"):
    """Return the Wyoming ``Info`` describing the ASR program."""
    attribution = Attribution(
        name="audio.cpp", url="https://github.com/0xShug0/audio.cpp"
    )
    program = AsrProgram(
        name="Wyoming Audio.cpp - asr",
        description="audio.cpp ASR bridge (non-streaming transcription)",
        installed=True,
        attribution=attribution,
        version=__version__,
        requires_external_vad=False,
        supports_transcript_streaming=False,
        models=[
            AsrModel(
                name=config.model,
                description=f"audio.cpp: {config.model}",
                installed=True,
                attribution=attribution,
                version=__version__,
                languages=[config.language or "auto"],
            )
        ],
    )

    return Info(asr=[program])
