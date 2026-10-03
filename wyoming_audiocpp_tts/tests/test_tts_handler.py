"""Tests for the Wyoming TTS event handler (AudioCppTtsEventHandler).

These drive the handler with Wyoming events and inspect the events it writes
back and the WAV it streams, mocking only the audio.cpp HTTP boundary
(audiocpp_client.synthesize) so no running audio.cpp is required.
"""

from unittest import mock

import pytest
import wave

from wyoming_audiocpp_tts import __version__, audiocpp_client
from wyoming_audiocpp_tts.config import Config, VoiceConfig
from wyoming_audiocpp_tts.tts_handler import AudioCppTtsEventHandler

from wyoming.event import Event
from wyoming.tts import Synthesize, SynthesizeStop, SynthesizeStopped

START = "audio-start"
CHUNK = "audio-chunk"
STOP = "audio-stop"


def types(events):
    return [event.type for event in events]


def data(events):
    return [event.data for event in events]


def build_handler(wav_path, voices=None):
    """Build a handler whose ``write_event`` records emitted events."""
    reader = mock.Mock()
    writer = mock.Mock()
    writer.writelines = mock.Mock()
    writer.write = mock.Mock()
    writer.drain = mock.AsyncMock(return_value=None)

    if voices is None:
        config = Config.from_args(None)
    else:
        config = Config(tts_voices=voices)

    handler = AudioCppTtsEventHandler(reader, writer, config, wav_path=str(wav_path))

    recorded: list = []
    async def capture_write_event(event):
        recorded.append(event)
        return await writer.drain()

    handler.write_event = capture_write_event
    return handler, recorded


def test_build_tts_info_empty():
    handler, _ = build_handler(None)
    assert handler._build_tts_info([]) == []


def test_build_tts_info_single_voice():
    handler, _ = build_handler(None)
    info = handler._build_tts_info(handler.config.tts_voices)
    assert len(info) == 1
    voice = info[0]
    assert voice.name == "omnivoice"
    assert voice.description == "omnivoice (omnivoice)"
    assert voice.languages == ["en"]
    assert voice.installed is True


def test_build_tts_info_multiple_voices():
    voices = [
        VoiceConfig(name="female", language="da"),
        VoiceConfig(name="male"),
    ]
    handler, _ = build_handler(None, voices=voices)
    info = handler._build_tts_info(voices)
    assert len(info) == 2
    assert info[0].name == "female"
    assert info[0].languages == ["da"]
    assert info[1].name == "male"
    assert info[1].languages == ["en"]
    assert info[0].description != info[1].description


async def test_describe_writes_info():
    handler, recorded = build_handler(None)
    await handler.handle_event(Event(type="describe"))

    assert types(recorded) == ["info"]
    info = data(recorded)[0]
    program = info["tts"][0]
    assert program["name"] == "Wyoming Audio.cpp - tts"
    assert program["installed"] is True
    assert program["description"] == "audio.cpp text-to-speech"
    assert program["version"] == __version__
    assert program["supports_synthesize_streaming"] is True
    assert len(program["voices"]) == 1
    assert program["voices"][0]["name"] == "omnivoice"


def test_find_voice_by_name():
    voices = [VoiceConfig(name="female"), VoiceConfig(name="male")]
    handler, _ = build_handler(None, voices=voices)
    assert handler._find_voice("female").voice_name == "female"
    assert handler._find_voice("male").voice_name == "male"


def test_find_voice_falls_back_to_first():
    voices = [VoiceConfig(name="female"), VoiceConfig(name="male")]
    handler, _ = build_handler(None, voices=voices)
    assert handler._find_voice("unknown").voice_name == "female"
    assert handler._find_voice(None).voice_name == "female"


async def test_synthesize_selects_voice_by_name(tmp_path):
    wav = tmp_path / "out.wav"
    voices = [VoiceConfig(name="female"), VoiceConfig(name="male")]
    handler, recorded = build_handler(wav, voices=voices)

    captured = {}

    def fake_synthesize(endpoint, voice, text):
        captured["voice"] = voice
        captured["text"] = text
        return audiocpp_client.WavFormat(sample_rate=24000, sampwidth=2, channels=1), [b"\x00" * 480]

    with mock.patch.object(audiocpp_client, "synthesize", fake_synthesize):
        await handler.handle_event(Synthesize(text="hej").event())
        assert captured["voice"].voice_name == "female"


async def test_synthesize_streams_audio_to_wav_and_events(tmp_path):
    wav = tmp_path / "out.wav"
    handler, recorded = build_handler(wav)

    def fake_synthesize(endpoint, voice, text):
        return audiocpp_client.WavFormat(sample_rate=24000, sampwidth=2, channels=1), [b"\x00" * 480]

    with mock.patch.object(audiocpp_client, "synthesize", fake_synthesize):
        await handler.handle_event(Synthesize(text="hej").event())
        assert types(recorded) == [START, CHUNK, STOP]

        with wave.open(str(wav), "rb") as read_wav:
            assert read_wav.getnframes() > 0


async def test_synthesize_single_audio_chunk(tmp_path):
    wav = tmp_path / "out.wav"
    handler, recorded = build_handler(wav)

    def fake_synthesize(endpoint, voice, text):
        return audiocpp_client.WavFormat(sample_rate=24000, sampwidth=2, channels=1), [b"\x00" * 480]

    with mock.patch.object(audiocpp_client, "synthesize", fake_synthesize):
        await handler.handle_event(Synthesize(text="hi").event())
        assert types(recorded) == [START, CHUNK, STOP]


async def test_synthesize_upstream_failure_terminates_stream_and_closes_wav(tmp_path):
    wav = tmp_path / "out.wav"
    handler, recorded = build_handler(wav)

    def fake_synthesize(endpoint, voice, text):
        raise RuntimeError("boom")

    with mock.patch.object(audiocpp_client, "synthesize", fake_synthesize):
        await handler.handle_event(Synthesize(text="hi").event())
        assert types(recorded) == [STOP]
        assert handler._wav is None


async def test_unknown_event_returns_true():
    handler, recorded = build_handler(None)
    result = await handler.handle_event(Event(type="unknown"))
    assert result is True
    assert recorded == []


async def test_synthesize_stop_acknowledged():
    """HA sends SynthesizeStop after AudioStop; we must reply with SynthesizeStopped."""
    handler, recorded = build_handler(None)
    await handler.handle_event(SynthesizeStop().event())
    assert len(recorded) == 1
    assert recorded[0].type == "synthesize-stopped"
