"""Tests for the Wyoming TTS event handler (AudioCppTtsEventHandler).

These drive the handler with Wyoming events and inspect the events it writes
back and the WAV it streams, mocking only the audio.cpp HTTP boundary
(audiocpp_client.synthesize) so no running audio.cpp is required.
"""

from unittest import mock

import pytest
import wave

from wyoming_audiocpp_tts import audiocpp_client
from wyoming_audiocpp_tts.config import Config
from wyoming_audiocpp_tts.tts_handler import AudioCppTtsEventHandler

from wyoming.event import Event
from wyoming.tts import Synthesize

START = "synthesize-start"
CHUNK = "synthesize-chunk"
STOP = "synthesize-stop"


def types(events):
    return [event.type for event in events]


def data(events):
    return [event.data for event in events]


def build_handler(wav_path):
    """Build a handler whose ``write_event`` records emitted events.

    ``AsyncEventHandler.write_event`` is the async wrapper that serializes the
    event through ``async_write_event``; wrapping it lets the test capture the
    exact events without needing a real socket writer.
    """
    reader = mock.Mock()
    writer = mock.Mock()
    writer.writelines = mock.Mock()
    writer.write = mock.Mock()
    writer.drain = mock.AsyncMock(return_value=None)

    config = Config.from_args(None, voice_overrides={"tts_voice0_model": "omnivoice"})
    handler = AudioCppTtsEventHandler(reader, writer, config)

    recorded: list = []
    async def capture_write_event(event):
        recorded.append(event)
        return await writer.drain()

    handler.write_event = capture_write_event
    return handler, recorded


def test_build_tts_info_none():
    handler, _ = build_handler(None)
    assert handler._build_tts_info(None) == []


def test_build_tts_info_voice():
    handler, _ = build_handler(None)
    info = handler._build_tts_info(handler.config.tts_voice)
    assert len(info) == 1
    voice = info[0]
    assert voice.name == "default"
    assert voice.description == "audio.cpp voice"
    assert voice.languages == ["en"]
    assert voice.installed is True


async def test_describe_writes_info():
    handler, recorded = build_handler(None)
    await handler.handle_event(Event(type="describe"))

    assert types(recorded) == ["info"]
    info = data(recorded)[0]
    program = info["tts"][0]
    assert program["name"] == "audio.cpp"
    assert program["installed"] is True
    assert program["description"] == "audio.cpp text-to-speech"
    assert program["version"] is None
    assert program["supports_synthesize_streaming"] is False
    assert len(program["voices"]) == 1
    assert program["voices"][0]["name"] == "default"


async def test_synthesize_streams_audio_to_wav_and_events(tmp_path):
    wav = tmp_path / "out.wav"
    handler, recorded = build_handler(wav)

    def fake_synthesize(endpoint, voice, text, **kwargs):
        yield b"PART1"
        yield b"PART2"

    with mock.patch.object(audiocpp_client, "synthesize", side_effect=fake_synthesize):
        await handler.handle_event(Synthesize(text="hello").event())

    assert types(recorded) == [START, CHUNK, CHUNK, STOP]
    # Wyoming TTS carries the audio in the WAV; the relayed text chunks are
    # empty placeholders.
    chunk_events = [e for e in recorded if e.type == CHUNK]
    assert all(e.data.get("text") == "" for e in chunk_events)

    with wave.open(handler._wav_path, "rb") as read_wav:
        assert read_wav.getnchannels() == 1
        assert read_wav.getsampwidth() == 2
        assert read_wav.getframerate() == 16000
        assert read_wav.getnframes() > 0


async def test_synthesize_single_audio_chunk(tmp_path):
    wav = tmp_path / "out.wav"
    handler, recorded = build_handler(wav)

    def fake_synthesize(endpoint, voice, text, **kwargs):
        yield b"\x00\x00"

    with mock.patch.object(audiocpp_client, "synthesize", side_effect=fake_synthesize):
        await handler.handle_event(Synthesize(text="hi").event())

    assert types(recorded) == [START, CHUNK, STOP]


async def test_synthesize_upstream_failure_terminates_stream_and_closes_wav(tmp_path):
    wav = tmp_path / "out.wav"
    handler, recorded = build_handler(wav)

    def fake_synthesize(endpoint, voice, text, **kwargs):
        raise RuntimeError("upstream audio.cpp error")

    with mock.patch.object(audiocpp_client, "synthesize", side_effect=fake_synthesize):
        with pytest.raises(RuntimeError):
            await handler.handle_event(Synthesize(text="hello").event())

    # The client stream must still be terminated and the WAV closed even when
    # the upstream audio.cpp call fails.
    assert types(recorded) == [START, STOP]
    assert handler._wav is None


async def test_unknown_event_returns_true():
    handler, recorded = build_handler(None)
    result = await handler.handle_event(Event(type="frobnicate"))

    assert result is True
    assert recorded == []
