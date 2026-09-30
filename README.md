# Wyoming audio.cpp ASR

A Wyoming protocol ASR service that bridges Home Assistant / Rhasspy to
[audio.cpp](https://github.com/0xShug0/audio.cpp). Wyoming clients connect
over TCP (`_wyoming._tcp.local.` mDNS discovery is opt-in via `--zeroconf`),
while the bridge accumulates the utterance, transcribes it through
audio.cpp's OpenAI-compatible transcription endpoint, and relays one
`Transcript` event back.

This is the ASR stage. The matching TTS stage is `wyoming-audiocpp-tts`.

## How it works

audio.cpp is an OpenAI-compatible HTTP server, not a Wyoming service. This
bridge converts between the two on every utterance:

- The service is a standard Wyoming `AsyncTcpServer` (default
  `tcp://0.0.0.0:55001`) speaking the Wyoming ASR event protocol
  (`Transcribe`, `AudioStart`, `AudioChunk`, `AudioStop` → `Transcript`).
- Audio is buffered as 16-bit/16 kHz mono PCM; on `AudioStop` the bridge
  calls `POST /v1/audio/transcriptions` and sends a single `Transcript`
  event before closing the connection (non-streaming).
- An optional demo browser web server (`--web-server`, requires the `web`
  extras) serves the same HTTP endpoints under `POST /api/speech-to-text`
  and `GET /api/info` for manual testing.

## Install

Editable install from the project root (creates the `wyoming-audiocpp-asr`
console script):

```bash
pip install -e .
```

Extras:

```bash
pip install -e ".[web]"      # demo browser web server (--web-server)
pip install -e ".[zeroconf]"  # mDNS discovery (--zeroconf)
pip install -e ".[dev]"       # dev deps (black, flake8, isort, pytest)
```

## Configure

Configuration is layered, later layers win: defaults, then `config.json`,
then `WYO_<FIELD>` environment variables, then command-line flags.

```json
{
  "audiocpp_uri": "http://localhost:8080",
  "model": "hviske",
  "language": "da",
  "uri": "tcp://0.0.0.0:55001",
  "enable_zeroconf": false,
  "web_server": false,
  "web_server_host": "127.0.0.1",
  "web_server_port": 5000
}
```

See [`config.example.json`](config.example.json) for the full set of keys.

audio.cpp is reached through its transcription endpoint:
`<audiocpp_uri>/v1/audio/transcriptions`.

## Run

The service is the Wyoming TCP server; `--zeroconf` (opt-in) registers
mDNS `_wyoming._tcp.local.` discovery for Home Assistant:

```bash
wyoming-audiocpp-asr --uri tcp://0.0.0.0:55001 --zeroconf

# Demo browser web server alongside the service (requires the 'web' extra):
wyoming-audiocpp-asr --uri tcp://0.0.0.0:55001 --web-server --web-server-port 5000
```

Options:

| Flag | Default | Meaning |
| --- | --- | --- |
| `--config` | `config.json` | Path to `config.json`. |
| `--uri` | `tcp://0.0.0.0:55001` | Wyoming TCP bind URI. |
| `--audiocpp-uri` | from `config.json` | Base URI of the audio.cpp server. |
| `--model` | `hviske` | audio.cpp model id to use. |
| `--language` | from `config.json` | Language hint for audio.cpp. |
| `--zeroconf` | off | Register mDNS `_wyoming._tcp.local.` discovery (requires the `zeroconf` extra). |
| `--web-server` | off | Also run the demo browser web server (requires the `web` extra). |
| `--web-server-host` | `127.0.0.1` | Interface for the demo web server. |
| `--web-server-port` | `5000` | Port for the demo web server. |
| `--web-server-allow` | — | Restrict the demo web server to these IP/CIDR values (repeatable); binds `0.0.0.0` when set. |
| `--debug` | off | Enable debug logging. |
| `--log-format` | basic format | Logging format. |
| `--version` | — | Print the bridge and wyoming version. |

## Develop

```bash
pytest
```


# Wyoming audio.cpp TTS

A Wyoming protocol TTS service that bridges Home Assistant / Rhasspy to
[audio.cpp](https://github.com/0xShug0/audio.cpp). Wyoming clients get a small,
event-protocol HTTP surface while the bridge talks to audio.cpp's OpenAI-compatible
speech endpoint and relays the audio result.

This is the TTS stage. The matching ASR stage is `wyoming-audiocpp-asr`.

## How it works

audio.cpp is an OpenAI-compatible HTTP server, not a Wyoming service. This bridge
converts between the two on every request:

- `POST /api/tts` — synthesize audio for the `text` field.
- `GET /` — report the configured TTS model, voice and ASR model.

Internally it calls `POST /v1/audio/speech` and returns the audio as
`audio/wav`.

## Install

Editable install from the project root (creates the `wyoming-audiocpp-tts`
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
command-line flags override them. The default voice (model `omnivoice`) is
optional; when omitted, supply it on the command line.

```json
{
  "audiocpp_uri": "http://localhost:8080",
  "asr_model": "hviske",
  "tts_voice": {
    "model": "omnivoice",
    "name": "female",
    "language": "da",
    "speed": 1.0
  }
}
```

audio.cpp is reached through its speech endpoint:
`<audiocpp_uri>/v1/audio/speech`.

```bash
wyoming-audiocpp-tts --config config.json --port 11201
```

Options:

| Flag | Default | Meaning |
| --- | --- | --- |
| `--config` | `config.json` | Path to `config.json`. |
| `--asr-model` | from `config.json` | audio.cpp model id used for transcription. |
| `--audiocpp-uri` | from `config.json` | Base URI of the audio.cpp server. |
| `--host` | `0.0.0.0` | Interface to bind. |
| `--port` | `11201` | Port to listen on. |
| `--log-level` | `INFO` | Logging level. |
| `--tts-voice0-model` | from `config.json` | TTS voice model id (e.g. `omnivoice`). |
| `--tts-voice0-name` | from `config.json` | Voice name sent as audio.cpp `voice`. |
| `--tts-voice0-language` | from `config.json` | Language hint (e.g. `da`). |
| `--tts-voice0-speed` | from `config.json` | Speaking rate multiplier. |
| `--tts-voice0-instruct` | from `config.json` | `instruct` field forwarded verbatim. |
| `--tts-voice0-extra-<key>` | — | Extra audio.cpp option (e.g. `--tts-voice0-extra-seed 42`). |

`--tts-voice0-*` flags override `config.json`; if none are given, the voice must
be configured in `config.json`, otherwise the service fails to start.

## Develop

```bash
pytest
```
## End-to-end tests

The bridge suite is `tests/test_e2e_bridges.py`. It starts isolated TTS and ASR
bridge subprocesses and uses `http://audio.cpp:8080` by default when that
service is reachable:

```bash
pytest -q tests/test_e2e_bridges.py
```
AUDIOCPP_URI=http://audio.cpp:8080 pytest -q tests/test_e2e_bridges.py
```
The playground smoke harness requires Node dependencies, Playwright's Chromium,
a running Next.js playground, and the bridge ports `11201` (TTS) and `11301` (ASR).
It uses mock bridges automatically when audio.cpp is unavailable; set
`AUDIOCPP_URI` to exercise real bridges instead:

```bash
cd wyoming_audiocpp_demo
npm install
npx playwright install chromium
./node_modules/.bin/next dev --port 11000
# In another shell, from the repository root:
python wyoming_audiocpp_demo/tests/smoke.py
```

The smoke harness intentionally tolerates the known React hydration warning and
empty model selector. It verifies the ASR model endpoint, TTS WAV response, and
playground TTS/ASR interactions without patching that playground bug.
