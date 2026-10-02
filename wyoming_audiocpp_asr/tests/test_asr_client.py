"""End-to-end test: the ASR bridge transcribes a real utterance for a real client.

Drives the actual ``AudioCppAsrEventHandler`` through a real ``AsyncTcpServer``
with a real ``wyoming.client.AsyncTcpClient``, feeding a canonical 16-bit/16 kHz
mono WAV from ``test_data`` and reading back the ``Transcript``. This exercises
the full Wyoming wire (client -> Transcribe/AudioStart/AudioChunk+/AudioStop ->
server -> Transcript) that the handler unit tests do not, and runs against the
real audio.cpp backend so the transcription is genuine.

The transcript is compared to the ground-truth label with a fuzzy word-recall
bar rather than an exact match: audio.cpp has a real error rate (it expands
abbreviations like ``lør-søn`` -> ``lørdag til søndag`` and rewords timestamps),
so the output is not 1:1 with the label. The test skips when audio.cpp is
unreachable, matching the rest of the e2e suite.
"""

import asyncio
import re
import wave
from pathlib import Path

import pytest
from wyoming.asr import Transcribe, Transcript
from wyoming.audio import AudioChunk, AudioStart, AudioStop
from wyoming.client import AsyncTcpClient
from wyoming.server import AsyncTcpServer

from ..config import Config
from ..server import handler_factory

AUDIOCPP_URI = "http://audio.cpp:8080"
DATA_DIR = Path(__file__).resolve().parent.parent.parent / "test_data"
CHUNK_BYTES = 65536  # ~256 ms of 16-bit mono
READ_TIMEOUT = 60.0
# Fuzzy bar: fraction of the label's words that appear in the transcript.
# Chosen well below the worst observed recall (~0.57) so ASR variance does not
# flake the test, while still catching an empty/garbage transcription.
MIN_LABEL_RECALL = 0.4


def _audiocpp_reachable() -> bool:
    import requests

    try:
        return requests.get(f"{AUDIOCPP_URI}/health", timeout=5).status_code == 200
    except Exception:
        return False


def _word_set(text: str) -> set:
    return set(re.findall(r"[a-zæøåé]+", text.lower()))


def _label_recall(label: str, transcript: str) -> float:
    label_words = _word_set(label)
    if not label_words:
        return 0.0
    return len(label_words & _word_set(transcript)) / len(label_words)


@pytest.fixture
async def server_and_port():
    """Run the ASR bridge on an ephemeral port; skip if audio.cpp is down."""
    if not _audiocpp_reachable():
        pytest.skip(f"audio.cpp not reachable at {AUDIOCPP_URI}")

    config = Config(audiocpp_uri=AUDIOCPP_URI)
    server = AsyncTcpServer("127.0.0.1", 0)
    await server.start(handler_factory(config))
    port = server._server.sockets[0].getsockname()[1]
    yield server, port
    await server.stop()
    server._server.close()


def _wav_files() -> list:
    return sorted(DATA_DIR.glob("*.wav"))


@pytest.mark.parametrize("wav_path", _wav_files())
async def test_asr_transcribes_wav(server_and_port, wav_path: Path):
    server, port = server_and_port
    label = (DATA_DIR / f"{wav_path.name}.txt").read_text().strip()

    with wave.open(str(wav_path), "rb") as w:
        rate, width, channels = w.getframerate(), w.getsampwidth(), w.getnchannels()
        frames = w.readframes(w.getnframes())

    async with AsyncTcpClient("127.0.0.1", port, read_timeout=READ_TIMEOUT) as client:
        await client.write_event(Transcribe(language="da").event())
        await client.write_event(
            AudioStart(rate=rate, width=width, channels=channels).event()
        )
        for i in range(0, len(frames), CHUNK_BYTES):
            await client.write_event(
                AudioChunk(
                    audio=frames[i:i + CHUNK_BYTES],
                    rate=rate,
                    width=width,
                    channels=channels,
                ).event()
            )
        await client.write_event(AudioStop().event())

        transcript = None
        while True:
            event = await client.read_event()
            if Transcript.is_type(event.type):
                transcript = Transcript.from_event(event)
                break

    assert transcript is not None, "no Transcript event received"
    text = transcript.text
    assert text.strip(), "transcript is empty"
    recall = _label_recall(label, text)
    assert recall >= MIN_LABEL_RECALL, (
        f"transcript too far from label (recall={recall:.2f} < {MIN_LABEL_RECALL}); "
        f"label={label!r}; transcript={text!r}"
    )
