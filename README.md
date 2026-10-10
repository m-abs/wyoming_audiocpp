# Wyoming audio.cpp Bridges

Wyoming protocol bridges that connect Home Assistant voice assistants to
[audio.cpp](https://github.com/0xShug0/audio.cpp).

Two services share a single `config.json`: the [**ASR bridge**](#asr-bridge) transcribes
speech into text, and the [**TTS bridge**](#tts-bridge) synthesizes text into speech.

## Integration with audio.cpp

[audio.cpp](https://github.com/0xShug0/audio.cpp) is a high-performance C++ audio inference framework built on top of ggml, designed to make modern local audio models practical, portable, and fast.

See [docs/integration.md](docs/integration.md) for the full protocol details,
event flows, and wire format.

## ASR Bridge

The ASR bridge speaks the Wyoming ASR protocol over TCP (default
`tcp://0.0.0.0:11301`, config field `asr_uri`). It buffers the utterance as
16-bit / 16 kHz mono PCM, calls `POST /v1/audio/transcriptions` on `AudioStop`,
and emits a single `Transcript` event before disconnecting. One response per request.

Config fields (ASR-specific):

| Field             | Default  | Meaning                                         |
| ----------------- | -------- | ----------------------------------------------- |
| `asr_model`       | `hviske` | audio.cpp model id for transcription.           |
| `asr_language`    | `da`     | Language hint; string or list of strings.       |
| `enable_zeroconf` | `false`  | Register mDNS `_wyoming._tcp.local.` discovery. |

## TTS Bridge

The TTS bridge speaks the Wyoming TTS protocol over TCP (default
`tcp://0.0.0.0:11201`, config field `tts_uri`). It calls `POST /v1/audio/speech`
with a streaming response, relays each audio batch as a `SynthesizeChunk`, and
guarantees `SynthesizeStop` even on upstream failure.

Config fields (TTS-specific):

| Field            | Default       | Meaning                                                        |
| ---------------- | ------------- | -------------------------------------------------------------- |
| `tts_voices`     | `[omnivoice]` | List of voice objects (model, name, language, speed, options). |
| `tts_web_server` | `false`       | Enable the demo Flask web server.                              |

## Docker images

Two images are published to GitHub Container Registry:

- `ghcr.io/m-abs/wyoming_audiocpp/asr` — ASR bridge
- `ghcr.io/m-abs/wyoming_audiocpp/tts` — TTS bridge

Both images share the same base and accept a single `config.json`. Each image
bakes in a default config at `/config/config.json`; mount your own to override:

```bash
docker run \
  -v /path/to/config.json:/config/config.json \
  ghcr.io/m-abs/wyoming_audiocpp/asr
```

The `audiocpp_uri` field can also be overridden via the `WYO_AUDIOPCPP_URI`
environment variable without editing the config file:

```bash
docker run \
  -e WYO_AUDIOPCPP_URI=http://my-audiocpp:8080 \
  ghcr.io/m-abs/wyoming_audiocpp/asr
```

### Docker Compose example

A full stack with both bridges and the audio.cpp backend:

```yaml
services:
  audiocpp:
    image: ghcr.io/0xshug0/audio.cpp:full-cuda12
    ports:
      - "8080:8080"
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: 1

  asr:
    image: ghcr.io/m-abs/wyoming_audiocpp/asr
    ports:
      - "11301:11301"
    volumes:
      - ./config.json:/config/config.json
    depends_on:
      - audiocpp

  tts:
    image: ghcr.io/m-abs/wyoming_audiocpp/tts
    ports:
      - "11201:11201"
    volumes:
      - ./config.json:/config/config.json
    depends_on:
      - audiocpp
```

## Development

### Setup

The devcontainer provides Python 3.14, Node, and the audio.cpp GPU service:

```bash
# Editable install (single distribution, both bridges):
pip install -e ".[dev]"

### Testing

```bash
# Unit + handler tests:
.venv/bin/python -m pytest

# E2E (requires audio.cpp or falls back to dead-upstream 502 path):
.venv/bin/python -m pytest tests/test_e2e_bridges.py
```

### Branching and publishing

Images are published via GitHub Actions:

- **`dev`** — feature development; no image builds.
- **`rc`** — merging `dev` → `rc` triggers a release-candidate build (e.g. `0.1.0-rc1`).
- **`main`** — merging `rc` → `main` triggers a release build (e.g. `0.1.0`, tagged `latest`).

The version is bumped manually in `pyproject.toml` as part of the release PR.
No direct push to `main`; all changes go through a PR.
