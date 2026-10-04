# Integration with audio.cpp

audio.cpp is an OpenAI-compatible HTTP server that serves speech models (ASR and TTS). It is **not** a Wyoming service — it speaks HTTP, not the Wyoming TCP event protocol. The bridges in this project convert between the two: they accept Wyoming events from Home Assistant clients over TCP, and relay the payload to audio.cpp's HTTP endpoints.

- [audio.cpp GitHub repo](https://github.com/0xShug0/audio.cpp)
- [Wyoming protocol docs](https://github.com/OHF-Voice/wyoming)

## HTTP endpoints

| Bridge | audio.cpp endpoint | Method | Request | Response |
| --- | --- | --- | --- | --- |
| ASR | `/v1/audio/transcriptions` | POST | multipart form: `file` (WAV), `model`, `language` | JSON: `{"text": ..., "language": ...}` |
| TTS | `/v1/audio/speech` | POST | JSON: `model`, `input` (text), `voice`, … | raw audio bytes (WAV) |

## ASR event flow

The ASR bridge implements the Wyoming ASR protocol. One utterance per connection:

```
Client → Bridge:  Transcribe (language hint)
Client → Bridge:  AudioStart
Client → Bridge:  AudioChunk × N   (16-bit / 16 kHz mono PCM)
Client → Bridge:  AudioStop
Bridge → Client:  Transcript        (single event, then disconnect)
```

The bridge buffers all `AudioChunk` data into an in-memory WAV. On `AudioStop` it calls `POST /v1/audio/transcriptions` (non-streaming) and emits one `Transcript` event before closing the connection.

## TTS event flow

The TTS bridge implements the Wyoming TTS protocol. One synthesis per connection:

```
Client → Bridge:  Synthesize (text, voice params)
Bridge → Client:  SynthesizeStart
Bridge → Client:  SynthesizeChunk × N   (audio batches, empty text)
Bridge → Client:  SynthesizeStop
```

The bridge calls `POST /v1/audio/speech` with a streaming response (`iter_content`). Each batch is written to a WAV file on disk and relayed as a `SynthesizeChunk`. A `finally` block guarantees `SynthesizeStop` is sent even if the upstream call fails.

## Wire framing

Wyoming events are framed as a JSON header followed by raw data bytes:

```
{"type":"<EventName>","data_length":N}
<N bytes of data>
```

The ASR bridge ships its own copy of this protocol in `wyoming_audiocpp_asr/wire.py`. The TTS bridge uses the `wyoming` package's server directly.
