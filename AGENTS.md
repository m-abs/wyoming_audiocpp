# Repository Guidelines

## Project Overview

Monorepo of **Wyoming protocol** bridges (Home Assistant voice assistant) to
[audio.cpp](https://github.com/0xShug0/audio.cpp). Two in-scope Python
distributions each translate the Wyoming event protocol into audio.cpp's
OpenAI-compatible HTTP endpoints, plus a Next.js 16 browser playground:

- `wyoming_audiocpp_asr` — ASR bridge; default bind `tcp://0.0.0.0:55001`.
- `wyoming_audiocpp_tts` — TTS bridge; default bind `tcp://0.0.0.0:10200`.

> **Scope note:** `wyoming-faster-whisper/` and `wyoming-piper/` are vendored
> **reference implementations only** — not project source. Do not edit them as
> if part of this repo; read them only to understand Wyoming handler patterns.

## Architecture & Data Flow

Both packages follow the same shape: a **Wyoming TCP server**
(`wyoming.server.AsyncTcpServer`) running an `AsyncEventHandler` subclass, plus
an optional Flask demo web server behind `--web-server`. The model backend is
never a Wyoming service — it is reached over HTTP.

**ASR flow** (`wyoming_audiocpp_asr/asr_handler.py`, `AudioCppAsrEventHandler`):
1. `Transcribe` → remember the requested language.
2. `AudioStart` → open an in-memory WAV (16-bit / 16 kHz mono).
3. `AudioChunk` → convert to canonical format, append audio.
4. `AudioStop` → transcribe **non-streaming** via
   `asyncio.to_thread(audiocpp_client.transcribe)`, emit one `Transcript`, then
   disconnect (return `False`). One response per request.
5. `Describe` → reply with service `Info`.

**TTS flow** (`wyoming_audiocpp_tts/tts_handler.py`, `AudioCppTtsEventHandler`):
- `Synthesize` → open a WAV **on disk**, emit `SynthesizeStart`, then stream
  audio.cpp's batched response (blocking call in an executor thread) — each batch
  is written to the WAV and relayed as an empty-text `SynthesizeChunk`. A
  `finally` always closes the WAV and sends `SynthesizeStop`, even on upstream
  failure. `Describe` → service `Info`.

**audio.cpp boundary** (`audiocpp_client.py` in each package) is the **only** code
that talks to audio.cpp, deliberately kept free of Wyoming types so it can be
tested without a running server:
- ASR: `transcribe(endpoint, wav_bytes, model, language)` → multipart
  `POST /v1/audio/transcriptions`, returns `{"text", "language"}`.
- TTS: `synthesize(...)` (streaming, `iter_content`) / `text_to_speech(...)` →
  JSON `POST /v1/audio/speech`, returns raw audio bytes.

**Wire framing:** ASR ships its own copy of the Wyoming byte-stream protocol in
`wyoming_audiocpp_asr/wire.py` (`{"type":..., "data_length":N}` header + raw data
bytes). TTS uses the `wyoming` package's server directly (no local wire module).

## Key Directories

| Path | Purpose |
| --- | --- |
| `wyoming_audiocpp_asr/` | ASR bridge package (root `pyproject.toml` = this dist) |
| `wyoming_audiocpp_tts/` | TTS bridge package (own `pyproject.toml`) |
| `wyoming_audiocpp_demo/` | Next.js 16 playground + in-process mock bridges |
| `tests/` | Root e2e suite (`test_e2e_bridges.py`) |
| `test_data/` | CC0 sample WAVs + transcript labels (deliberately non-canonical) |
| `.devcontainer/` | Dev container: Python 3.14 app + audio.cpp GPU service |
| `wyoming-faster-whisper/`, `wyoming-piper/` | Reference impls (vendored, not project source) |

## Development Commands

Run **all** Python via `.venv/bin/python` from the repo root — never system
python. The workspace is a devcontainer at `/workspaces`.

```bash
# Install (two separate distributions)
pip install -e .                        # ASR -> console script wyoming-audiocpp-asr; extras [web] [zeroconf] [dev]
cd wyoming_audiocpp_tts && pip install -e .   # TTS -> wyoming-audiocpp-tts; extras [dev] [web] (no zeroconf)

# Run the bridges (Wyoming TCP services)
.venv/bin/python -m wyoming_audiocpp_asr --uri tcp://0.0.0.0:55001 \
    --audiocpp-uri http://audio.cpp:8080 --model hviske --language da [--zeroconf] [--web-server]
.venv/bin/python -m wyoming_audiocpp_tts --uri tcp://0.0.0.0:10200 \
    --tts-voice0-model omnivoice [--tts-voice0-extra-seed 42] [--zeroconf] [--web-server]

# Tests (pytest, asyncio_mode=auto)
.venv/bin/python -m pytest              # root e2e + per-package tests
.venv/bin/python -m pytest wyoming_audiocpp_asr/tests   # or the tts dir

# Demo playground (Node/npm; see Runtime below)
cd wyoming_audiocpp_demo && npm install && npx playwright install chromium
./node_modules/.bin/next dev --port 11000
.venv/bin/python wyoming_audiocpp_demo/tests/smoke.py   # from repo root; auto-falls back to mock bridges
```

Lint/format is configured **per distribution** in each `pyproject.toml`
(`[tool.black]` line-length 88, `[tool.isort] profile="black"`); flake8 via the
`dev` extra. There is no repo-wide formatter config.

## Code Conventions & Common Patterns

- **Config layering (both packages):** dataclass field defaults → `config.json`
  → `WYO_<FIELD>` env vars → CLI overrides, last wins. `Config.from_args(path,
  **overrides)` ignores `None` overrides so an absent flag keeps the lower-layer
  value; `validate()` raises `ValueError` on bad values. TTS adds a nested
  `tts_voice: VoiceConfig` merged via `_merge_voice` (its `extra` dict merges
  additively). See `wyoming_audiocpp_asr/config.py`,
  `wyoming_audiocpp_tts/config.py`.
- **Event handlers** subclass `wyoming.server.AsyncEventHandler`;
  `handle_event` returns a bool (`True` stay connected, `False` disconnect).
  Blocking HTTP always runs off the event loop via `asyncio.to_thread` /
  `loop.run_in_executor` so it never stalls other clients.
- **Error handling:** upstream failures are relayed to the Wyoming client — ASR
  catches the exception and writes an `Error` event, then still closes the
  utterance; TTS relies on a `finally` to terminate the stream and release the
  WAV file handle.
- **Optional deps via extras** (`web`=flask, `zeroconf`, `dev`): imports are
  guarded so a missing extra is a clean startup error (`parser.error` / `return
  2`), not an import-time crash of the default entry point.
- **Logging:** `logging.getLogger("wyoming_audiocpp_asr" | "wyoming_audiocpp_tts")`;
  `basicConfig` in `__main__` with `--debug` / `--log-format`.
- **Naming:** packages `wyoming_audiocpp_{asr,tts}`; console scripts
  `wyoming-audiocpp-{asr,tts}`; handlers `AudioCpp{Asr,Tts}EventHandler`; config
  types `Config` / `VoiceConfig`.

## Important Files

- **Entry points (console scripts):** `wyoming_audiocpp_asr/__main__.py`,
  `wyoming_audiocpp_tts/__main__.py` — argparse CLIs, logging setup, web-server
  bootstrap, then start the TCP server.
- **TCP servers:** `wyoming_audiocpp_asr/server.py` (`create_tcp_server`),
  `wyoming_audiocpp_tts/server.py`.
- **Handlers:** `wyoming_audiocpp_asr/asr_handler.py`,
  `wyoming_audiocpp_tts/tts_handler.py`.
- **Wire framing:** `wyoming_audiocpp_asr/wire.py` (ASR only).
- **Config:** `wyoming_audiocpp_asr/config.py`, `wyoming_audiocpp_tts/config.py`.
- **audio.cpp clients:** `wyoming_audiocpp_asr/audiocpp_client.py`,
  `wyoming_audiocpp_tts/audiocpp_client.py`.
- **HTTP demo bridges:** `wyoming_audiocpp_asr/asr_server.py`,
  `wyoming_audiocpp_tts/tts_server.py`; **web servers:** `.../web_server.py`.
- **Packaging:** root `pyproject.toml` (ASR dist), `wyoming_audiocpp_tts/pyproject.toml` (TTS dist).
- **Config example / debug:** `config.example.json`, `.vscode/launch.json`
  (debug configs use `--uri`, matching current code).

## Runtime/Tooling Preferences

- **Python** `>=3.11` (per `pyproject.toml`); devcontainer runs CPython **3.14**
  (`python:3-3.14-bookworm`). Always `.venv/bin/python`.
- **Demo:** Node via nvm (workspace pins v24.21.0), **npm** — the committed
  `package-lock.json` is canonical (not pnpm/yarn). Stack: Next.js 16.3.6,
  React 19.2.8, TypeScript ^5, Tailwind v4, Playwright ^1.63.
- **audio.cpp backend:** GPU service `ghcr.io/0xshug0/audio.cpp:full-cuda12` on
  `:8080`, models `omnivoice` (TTS) + `hviske` (ASR); OpenAI-compatible API.
- No in-scope package ships a Dockerfile (only the reference impls do).

## Testing & QA

- **Framework:** pytest + pytest-asyncio (`asyncio_mode = "auto"`). Per-package
  unit/handler/HTTP tests mock `audiocpp_client` via monkeypatch; plus wire
  round-trips and config-layering tests.
- **e2e:** root `tests/test_e2e_bridges.py` launches real bridge subprocesses
  against audio.cpp (skipped if unreachable) or a dead upstream for the 502
  path. Demo has a Playwright harness (`wyoming_audiocpp_demo/tests/smoke.py`)
  that auto-falls back to in-process mock bridges
  (`mock_bridges.py` / `tests/mock_runner.py`).
- **Fixtures:** `test_data/` — HuggingFace `alexandrainst/nota`, CC0; WAVs are
  float32/44.1 kHz stereo *on purpose* (non-canonical) to exercise format
  constraints.
- **Coverage expectation:** no coverage gate. New behavior should add a focused
  test mirroring the per-package layout (handler, server, web_server, config,
  client).

### Known staleness (verify before relying on docs/tests)

- `tests/test_e2e_bridges.py` and the README TTS section still pass
  `--host/--port`, but the current `wyoming_audiocpp_tts/__main__.py` is a
  Wyoming TCP service taking **`--uri`** (`.vscode/launch.json` matches code).
  The e2e test will fail on argparse as written.
- README says "editable install from the project root creates the
  `wyoming-audiocpp-tts` console script" — **stale**: the root `pyproject.toml`
  defines only the ASR dist; TTS must be installed from
  `wyoming_audiocpp_tts/`. Confirm with `pip show wyoming-audiocpp-tts`.
- No in-scope `CHANGELOG.md` exists (only reference impls have them); the de-facto
  record is `README.md` + dated docs under `.agents/plans/` and `.agents/review/`.

## Plans

First step efter approving a plan, the plan must be saved in `.agents/plans` and named `<DATE>_<NAME>.md`:

- Directory: `.agents/plans`
- Prefix: date (`YYYY-MM-DD`)
- Name: all uppercase, spaces replaced with `_`

Example: `.agents/plans/2026-09-27_WYOMING_AUDIOCPP_ASR_PLAN.md`.

## Review and review fixes

Reviews and result from review fixes must be saved to `.agents/review` and named similar to plans.

Example: `.agents/review/2026-09-27_WYOMING_AUDIOCPP_ASR_REVIEW_FIXES.md`.
