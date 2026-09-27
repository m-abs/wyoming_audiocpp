# Wyoming audio.cpp ASR

A Wyoming protocol ASR service that bridges Home Assistant / Rhasspy to
[audio.cpp](https://github.com/0xShug0/audio.cpp). Wyoming clients get a small,
event-protocol HTTP surface while the bridge talks to audio.cpp's
OpenAI-compatible transcription endpoint and relays the result.

This is the ASR stage. The matching TTS stage is `wyoming-audiocpp-tts`.

## How it works

audio.cpp is an OpenAI-compatible HTTP server, not a Wyoming service. This
bridge converts between the two on every request:

- `POST /api/speech-to-text` — transcribe an uploaded WAV to text.
- `GET /api/info` — list the ASR models audio.cpp exposes.

Internally it calls `POST /v1/audio/transcriptions` and returns
`{"text": ..., "language": ...}` as a Wyoming event.

## Install

Editable install from the project root (creates the `wyoming-audiocpp-asr`
console script):

```bash
pip install -e .
```

Dev deps (black, flake8, isort, pytest):

```bash
pip install -e ".[dev]"
```

## Configure

Configuration is layered: `config.json` provides defaults and project settings,
command-line flags override them.

```json
{
  "audiocpp_uri": "http://localhost:8080",
  "model": "hviske",
  "language": "da"
}
```

See [`config.example.json`](config.example.json) for the full set of keys.

audio.cpp is reached through its transcription endpoint:
`<audiocpp_uri>/v1/audio/transcriptions`.

## Run

```bash
wyoming-audiocpp-asr --config config.json --port 5000
```

Options:

| Flag | Default | Meaning |
| --- | --- | --- |
| `--config` | `config.json` | Path to `config.json`. |
| `--audiocpp-uri` | from `config.json` | Base URI of the audio.cpp server. |
| `--model` | `hviske` | audio.cpp model id to use. |
| `--language` | from `config.json` | Language hint for audio.cpp. |
| `--host` | `0.0.0.0` | Interface to bind. |
| `--port` | `5000` | Port to listen on. |
| `--log-level` | `INFO` | Logging level. |

## Develop

```bash
pytest
```
