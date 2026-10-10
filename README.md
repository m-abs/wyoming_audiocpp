# Wyoming audio.cpp Bridges

Use [audio.cpp](https://github.com/0xShug0/audio.cpp) as the speech recognition
and text-to-speech engine for Home Assistant Voice. These bridges connect
audio.cpp to Home Assistant over the [Wyoming protocol](https://www.home-assistant.io/integrations/wyoming/),
the same way the Whisper and Piper voice services do.

One distribution ships two services, sharing a single `config.json`:

- the [**ASR bridge**](#asr-bridge) turns speech into text
- the [**TTS bridge**](#tts-bridge) turns text into speech

Point the Home Assistant **Wyoming Protocol** integration at the bridge's host
and port. See [docs/integration.md](docs/integration.md) for the event flows and
wire format.

## About audio.cpp

[audio.cpp](https://github.com/0xShug0/audio.cpp) is a high-performance C++ audio
inference framework built on top of `ggml`, designed to make modern local audio
models practical, portable, and fast. These bridges only need its
OpenAI-compatible HTTP endpoints; see the upstream repository for the models,
backends, and tooling it supports.

## ASR Bridge

The ASR bridge binds the Wyoming ASR protocol on TCP (default
`tcp://0.0.0.0:11301`). It buffers the utterance as 16-bit / 16 kHz mono PCM,
calls `POST /v1/audio/transcriptions` on `AudioStop`, emits a single
`Transcript` event, then disconnects — one response per request. Upstream
failures are relayed to the Wyoming client as an `Error` event.

## TTS Bridge

The TTS bridge binds the Wyoming TTS protocol on TCP (default
`tcp://0.0.0.0:11201`). It opens the output WAV, sends `SynthesizeStart`, then
streams audio.cpp's batched response, relaying each batch as a
`SynthesizeChunk`. `SynthesizeStop` is always sent, even when audio.cpp fails
mid-stream.

## Configuration

Both bridges resolve settings in layers, last one wins:

1. dataclass defaults
2. `config.json` (`--config` path, default `./config.json`)
3. `WYO_<FIELD>` environment variables
4. command-line flags

`config.example.json` is a complete working example.

Shared fields:

| Field             | Default                 | Meaning                                         |
| ----------------- | ----------------------- | ----------------------------------------------- |
| `audiocpp_uri`    | `http://localhost:8080` | Base URI of the audio.cpp HTTP server.          |
| `enable_zeroconf` | `false`                 | Register mDNS `_wyoming._tcp.local.` discovery. |
| `log_level`       | `INFO`                  | `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`. |

ASR-specific:

| Field                  | Default                 | Meaning                                              |
| ---------------------- | ----------------------- | ---------------------------------------------------- |
| `asr_uri`              | `tcp://0.0.0.0:11301`   | Wyoming TCP bind URI.                                |
| `asr_model`            | `hviske`                | audio.cpp model id for transcription.                |
| `asr_language`         | `da`                    | Language hint; string or list of language codes.     |
| `asr_web_server`       | `false`                 | Also run the demo browser web server (`web` extra). |
| `asr_web_server_host`  | `127.0.0.1`             | Demo web server interface.                           |
| `asr_web_server_port`  | `5000`                  | Demo web server port.                                |
| `asr_web_server_allow` | `null`                  | IP/CIDR allow-list for the demo web server.          |

TTS-specific:

| Field                  | Default                 | Meaning                                              |
| ---------------------- | ----------------------- | ---------------------------------------------------- |
| `tts_uri`              | `tcp://0.0.0.0:11201`   | Wyoming TCP bind URI.                                |
| `tts_voices`           | `[omnivoice]`           | Voice objects: `model`, `name`, `language`, `speed`, `options`. |
| `tts_web_server`       | `false`                 | Also run the demo browser web server (`web` extra). |
| `tts_web_server_host`  | `127.0.0.1`             | Demo web server interface.                           |
| `tts_web_server_port`  | `5001`                  | Demo web server port.                                |
| `tts_web_server_allow` | `null`                  | IP/CIDR allow-list for the demo web server.          |

Voices are the only field that cannot be set from the environment or the
command line; they must come from `config.json`.

```bash
# Run the bridges against a local audio.cpp. Model and language come from
# config.json or WYO_ASR_MODEL / WYO_ASR_LANGUAGE; --asr-uri and --audiocpp-uri
# are the only CLI overrides.
.venv/bin/python -m wyoming_audiocpp_asr \
    --asr-uri tcp://0.0.0.0:11301 \
    --audiocpp-uri http://localhost:8080

.venv/bin/python -m wyoming_audiocpp_tts \
    --tts-uri tcp://0.0.0.0:11201 \
    --audiocpp-uri http://localhost:8080
```

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

A full stack — audio.cpp backend plus both bridges, with the model packages
mounted at `/app/models` — is in [example/](example/):

```bash
cd example
hf download audio-cpp/audio.cpp-gguf OmniVoice-GGUF Hviske-v5.3-GGUF --local-dir ./models
docker compose up -d
```

`example/docker-compose.yml`, `example/server.json` (audio.cpp model config) and
`example/config.json` (shared bridge config) are documented in
[example/README.md](example/README.md).

## Development

### Setup

The devcontainer provides Python 3.14, Node, and the audio.cpp GPU service:

```bash
# Editable install (single distribution, both bridges):
pip install -e ".[dev]"
```

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

The version is bumped in `pyproject.toml` as part of the release PR using
`scripts/bump_version.py`:

```bash
# Show the current version:
.venv/bin/python scripts/bump_version.py --show

# Set the target release version (e.g. 0.3.0):
.venv/bin/python scripts/bump_version.py --set 0.3.0

# Bump the base version (patch / minor / major):
.venv/bin/python scripts/bump_version.py --bump minor
```

RC versions (`0.3.0-rc1`) are computed by the workflow on push to `rc`. The
workflow skips publishing a new RC once the base version is already published
on ghcr.io — e.g. if `0.2.0` is published, `rc` pushes do not publish
`0.2.0-rc2`. No direct push to `main`; all changes go through a PR. See
[docs/adr/0002-branching-strategy-dev-rc-main.md](docs/adr/0002-branching-strategy-dev-rc-main.md)
for the full rationale.
