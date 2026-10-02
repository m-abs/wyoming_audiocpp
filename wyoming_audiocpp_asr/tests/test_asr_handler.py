"""Tests for AudioCppAsrEventHandler over the Wyoming event protocol."""

from __future__ import annotations

import json
import pytest

from wyoming.asr import Transcribe, Transcript
from wyoming.audio import AudioChunk, AudioStart, AudioStop
from wyoming.error import Error
from wyoming.event import Event
from wyoming.info import Describe, Info

from wyoming_audiocpp_asr import audiocpp_client
from wyoming_audiocpp_asr.asr_handler import AudioCppAsrEventHandler, build_asr_info
from wyoming_audiocpp_asr.config import Config

MODEL = "hviske"

_CHUNK = AudioChunk(rate=16000, width=2, channels=1, audio=b"\x00" * 160).event()
_START = AudioStart(rate=16000, width=2, channels=1).event()


def _config(**overrides) -> Config:
    return Config.from_args(None, model=MODEL, **overrides)


class _Writer:
    """Collects events written by the handler (a minimal StreamWriter)."""

    def __init__(self) -> None:
        self.events: list[Event] = []
        self._buf = bytearray()

    def writelines(self, chunks) -> None:
        for chunk in chunks:
            self._buf.extend(chunk)

    def write(self, data) -> None:
        self._buf.extend(data)

    async def drain(self) -> None:
        # Frame layout: {"type": ..., "data_length": n, "payload_length": m}\n
        # + data JSON bytes + raw payload bytes.
        while True:
            newline = self._buf.find(b"\n")
            if newline < 0:
                return
            head = json.loads(bytes(self._buf[:newline]).decode("utf-8"))
            data_length = int(head.get("data_length", 0))
            payload_length = int(head.get("payload_length", 0))
            data_start = newline + 1
            event = Event(
                type=head["type"],
                data=(
                    json.loads(bytes(self._buf[data_start : data_start + data_length]).decode("utf-8"))
                    if data_length
                    else {}
                ),
                payload=bytes(
                    self._buf[data_start + data_length : data_start + data_length + payload_length]
                ),
            )
            self.events.append(event)
            del self._buf[: data_start + data_length + payload_length]

    def close(self) -> None:
        pass

    async def wait_closed(self) -> None:
        pass

    def types(self) -> list[str]:
        return [event.type for event in self.events]

    def first(self, type_str: str) -> Event:
        for event in self.events:
            if event.type == type_str:
                return event
        raise AssertionError(f"no {type_str} event written; got {self.types()}")


async def _run(handler: AudioCppAsrEventHandler, events: list[Event]) -> bool:
    """Feed events one at a time; stop when the handler disconnects."""
    keep = True
    for event in events:
        keep = await handler.handle_event(event)
        if not keep:
            break
    return keep


@pytest.fixture
def writer():
    return _Writer()


@pytest.fixture
def handler(writer):
    return AudioCppAsrEventHandler(None, writer, _config())


def _fake_transcribe(captured: dict, **result):
    def fake(endpoint, wav_bytes, model, language, *, timeout=120.0):
        captured.update(endpoint=endpoint, model=model, language=language)
        assert endpoint.endswith("/v1/audio/transcriptions")
        assert wav_bytes[:4] == b"RIFF", "bridge must send a well-formed WAV"
        return result

    return fake


async def test_handle_transcribe(handler, writer, monkeypatch):
    """Transcribe language wins, audio is transcribed, and the connection
    drops after the single Transcript response."""
    captured: dict = {}
    monkeypatch.setattr(
        audiocpp_client, "transcribe", _fake_transcribe(captured, text="hej", language="en")
    )

    keep = await _run(
        handler,
        [
            Transcribe(language="en").event(),
            _START,
            _CHUNK,
            AudioStop().event(),
        ],
    )

    assert keep is False, "handler must disconnect after one response"
    transcript = Transcript.from_event(writer.first("transcript"))
    assert transcript.text == "hej"
    assert transcript.language == "en"
    assert captured["model"] == MODEL
    assert captured["language"] == "en"


async def test_handle_transcribe_language_auto_falls_back_to_config(
    handler, writer, monkeypatch
):
    """A client 'auto' (or absent) sends the config.language hint instead."""
    captured: dict = {}
    monkeypatch.setattr(
        audiocpp_client,
        "transcribe",
        _fake_transcribe(captured, text="hej", language="da"),
    )

    for transcribe_event in (
        Transcribe(language="auto").event(),
        Transcribe(language=None).event(),
    ):
        handler = AudioCppAsrEventHandler(None, writer, _config())
        await _run(handler, [transcribe_event, _START, _CHUNK, AudioStop().event()])

    assert captured["language"] == "da"


async def test_handle_audio_stop_empty(handler, writer, monkeypatch):
    """AudioStop with no audio sends an empty Transcript, never transcribes."""
    monkeypatch.setattr(
        audiocpp_client,
        "transcribe",
        lambda *a, **kw: pytest.fail("transcribe must not be called without audio"),
    )

    keep = await _run(handler, [AudioStop().event()])

    assert keep is False
    transcript = Transcript.from_event(writer.first("transcript"))
    assert transcript.text == ""


async def test_handle_describe(handler, writer):
    """Describe returns the service Info with the audio.cpp ASR program."""
    keep = await _run(handler, [Describe().event()])
    assert keep is True, "Describe keeps the connection open"

    info = Info.from_event(writer.first("info"))
    assert len(info.asr) == 1
    assert info.asr[0].name == "Wyoming Audio.cpp - asr"
    assert info.asr[0].installed is True
    assert info.asr[0].models[0].name == MODEL
    assert info.asr[0].requires_external_vad is False
    assert info.asr[0].supports_transcript_streaming is False


async def test_handle_transcribe_error_surfaces_error_event(
    handler, writer, monkeypatch
):
    """An audio.cpp failure is relayed to the client as an Error event."""

    def broken(*args, **kwargs):
        raise ConnectionError("audio.cpp down")

    monkeypatch.setattr(audiocpp_client, "transcribe", broken)

    keep = await _run(handler, [_START, _CHUNK, AudioStop().event()])

    assert keep is False
    error = Error.from_event(writer.first("error"))
    assert "audio.cpp transcription failed" in error.text
    assert "transcript" not in writer.types()


def test_build_asr_info_uses_config_language():
    info = build_asr_info(_config(language="sv"))
    assert info.asr[0].models[0].languages == ["sv"]

    info = build_asr_info(_config())
    assert info.asr[0].models[0].languages == ["da"]


async def test_disconnect_closes_open_utterance(handler, writer):
    """A client that drops mid-utterance does not leak the WAV buffer."""
    await handler.handle_event(_START)
    assert handler._wav is not None
    await handler.disconnect()
    assert handler._wav is None
    assert writer.events == []
