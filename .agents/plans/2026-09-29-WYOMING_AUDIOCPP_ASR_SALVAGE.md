# wyoming-audiocpp-asr-plan

## Context

`wyoming_audiocpp_asr` currently ships as a Flask HTTP server exposing REST endpoints (`POST /api/speech-to-text`, `POST /api/info`). Home Assistant and Rhasspy do not use this REST surface — they use the Wyoming protocol: an `AsyncTcpServer` listening on a TCP port and advertising itself via mDNS `_wyoming._tcp.local.` discovery. The ASR bridge has no zeroconf registration and no Wyoming event protocol, so it is invisible to HA/Rhasspy.

End state: the ASR bridge becomes a real Wyoming service — `wyoming.AsyncTcpServer` over TCP with opt-in `HomeAssistantZeroconf` mDNS registration, an `AsyncEventHandler` that turns Wyoming ASR events into calls to audio.cpp, and a CLI that starts the TCP server by default. The existing Flask server (`asr_server.py`) is KEPT as an optional demo HTTP server, started only with `--web-server`, and a browser-facing demo UI (`web_server.py`) is added as a `--web-server` add-on (like `wyoming-piper`). Discovery reference: https://github.com/OHF-Voice/wyoming-faster-whisper and https://github.com/OHF-Voice/wyoming-piper checked out in /tmp.

## Approach

### Step 1: ASR event handler

**File**: `wyoming_audiocpp_asr/asr_handler.py` (new)

**Symbol**: `AudioCppAsrEventHandler(AsyncEventHandler)`.

**Methods** (mirrors `wyoming_faster_whisper.DispatchEventHandler`, the ASR reference):

- `handle_event(self, event: Event) -> bool`:
  - `AudioStart.is_type(event.type)` → create VAD endpoint detector (reuse `wyoming.endpointing.SileroEndpointDetector`), return `True`.
  - `AudioChunk.is_type(event.type)` → convert chunk via `wyoming.audio.AudioChunkConverter` (rate 16000, width 2, channels 1), write raw bytes to a `tempfile.TemporaryDirectory()` WAV path using `wave.Wave_write`, return `True`.
  - `AudioStop.is_type(event.type)` → close WAV, call `audiocpp_client.transcribe()` with the WAV bytes and configured `model`/`language`; send `wyoming.asr.Transcript(text=..., language=...).event()`; return `False` (disconnect after the single response).
  - `Transcribe.is_type(event.type)` → set `self._language = Transcribe.from_event(event).language` (auto-detect if `AUTO_LANGUAGE`/None), return `True`.
  - `Describe.is_type(event.type)` → send service-info event; reuse `build_asr_info()` (new) and `write_event`.
  - any other type → return `True` (stay connected).

**Reuse**: `wyoming_audiocpp_asr/audiocpp_client.py::transcribe()` (unchanged), `wyoming_audiocpp_asr/config.py::Config` (unchanged), `wyoming.asr.Transcribe`, `wyoming.asr.Transcript`, `wyoming.audio.AudioChunk`, `wyoming.audio.AudioChunkConverter`.

**New helper**: `build_asr_info(config: Config) -> Info` returns `wyoming.info.Info(asr=[AsrProgram(name="audio.cpp", description=..., attribution=Attribution(name="audio.cpp", url="https://github.com/0xShug0/audio.cpp"), installed=True, models=[AsrModel(name=config.model, description=f"audio.cpp: {config.model}", attribution=..., installed=True, languages=[config.language or "auto"])])])` — mirrors `wyoming_faster_whisper.build_info()`.

### Step 2: Wyoming TCP server (replaces Flask server as the default)

**File**: `wyoming_audiocpp_asr/server.py` (new; `asr_server.py` KEPT, not deleted).

**Symbols**:
- `create_handler(config: Config) -> AudioCppAsrEventHandler` → `return AudioCppAsrEventHandler(config)`.
- `create_tcp_server(config: Config)`:
  - `from wyoming.server import AsyncServer, AsyncTcpServer`
  - `from wyoming.zeroconf import HomeAssistantZeroconf`
  - `uri = config.uri` (parse host/port from the `tcp://host:port` string)
  - `server = AsyncServer.from_uri(uri)`
  - if not disabled: `assert isinstance(server, AsyncTcpServer); hass_zeroconf = HomeAssistantZeroconf(name=config.zeroconf_name or "wyoming-audiocpp-asr", port=server.port, host=server.host); asyncio.create_task(hass_zeroconf.register_server())`
  - `asyncio.run(server.run(partial(create_handler, config)))`

**Behavior**: no Flask import in `server.py` or `__main__.py`. `asr_server.py` (Flask) is kept verbatim and imported only by `web_server.py`/`__main__.py` when `--web-server` is given.

### Step 3: Demo web server (browser UI alongside the Wyoming service)

**File**: `wyoming_audiocpp_asr/web_server.py` (new).

**Symbols**:
- `make_asr_web_server(config: Config, flask_app: Flask) -> Flask` — reuses `asr_server.create_app(config)` (the existing Flask `/api/speech-to-text` and `/api/info` endpoints, unchanged) and adds browser routes:
  - `GET /` → HTML form: a textarea (text) and an `<input type="file" accept="audio/*">`, plus a "Transcribe" button. The form posts a multipart WAV file to `/api/speech-to-text`; the handler shows the `text` result.
  - `GET /health` → `{"status": "ok"}` (mirrors `wyoming-piper`'s `/health`).
  - `GET /api/status` → `{"service": "wyoming-audiocpp-asr", "model": config.model, "language": config.language}` (mirrors `wyoming-piper`'s `/api/status`).
- `run_web_server(flash_app: Flask, host: str, port: int) -> threading.Thread` — runs the Flask app in a daemon thread (reuse `wyoming_piper.web_server.run_web_server` pattern: bind the socket, `werkzeug.serving.make_server(..., fd=sock.fileno())`, log level `ERROR`, return thread).

**Behavior**: reuses `asr_server.create_app`'s existing CORS after-request hook; no new audio.cpp logic.

### Step 4: CLI entry point

**File**: `wyoming_audiocpp_asr/__main__.py` — replace the Flask `app.run(...)` invocation.

**CLI flags** (mirror `wyoming-faster-whisper --help`):
- `--uri` (required) — `tcp://host:port`, default `tcp://0.0.0.0:55001`.
- `--web-server` (optional `action="store_true"`) — run the demo browser web server in a background thread (requires the `web` optional dependencies: Flask + `werkzeug`).
- `--web-server-host` (optional, default `127.0.0.1`) — interface for the demo web server.
- `--web-server-port` (optional int, default `5000`) — port for the demo web server.
- `--web-server-allow` (optional `action="append"`) — restrict the demo web server to these IP addresses/CIDRs (repeatable), since the UI has no authentication.
- `--zeroconf` (optional `action="store_true"`) — register mDNS `_wyoming._tcp.local.` discovery as `<name>` (default: the `--uri` host or `wyoming-audiocpp-asr`).
- `--debug` / `--log-format` / `--version` — logging/version.

**Entry flow**: `args = parse_args()`, `logging.basicConfig(...)`, `server = AsyncServer.from_uri(args.uri)`, register zeroconf via `HomeAssistantZeroconf(name=args.zeroconf, port=server.port, host=server.host)` and `asyncio.create_task(...)` if set, then `asyncio.run(server.run(partial(start_handler, config_from_args)))`. If `args.web_server`, start `run_web_server(make_asr_web_server(config_from_args), args.web_server_host, args.web_server_port)` in a background thread BEFORE the Wyoming server (the UI only reads directories, so it does not need the backend, and a missing dependency or an unavailable port should fail now rather than after the wait).

### Step 5: Config layer

**File**: `wyoming_audiocpp_asr/config.py` — add fields to `Config`:
- `uri: str = "tcp://0.0.0.0:55001"` — Wyoming TCP bind.
- `enable_zeroconf: bool = False` — whether to register mDNS discovery.
- `zeroconf_name: Optional[str] = None` — mDNS service name (defaults to the URI host, else `wyoming-audiocpp-asr`).
- `web_server: bool = False` — whether to also start the demo web server.
- `web_server_host: str = "127.0.0.1"`, `web_server_port: int = 5000`, `web_server_allow: Optional[List[str]] = None` — demo web server settings.

Keep the existing `audiocpp_uri`, `model`, `language` fields (used by `asr_server.py`/`audiocpp_client.py`). The layered `Config.from_args()` precedence is CLI > env var `WYO_...` > `config.json` > default.

**`Config` validation**: add `web_server_port` must be > 0 if `web_server`; `uri` must parse as a `tcp://` host/port when starting the Wyoming service.

## Critical files & anchors

- `wyoming_audiocpp_asr/asr_handler.py` — new `AudioCppAsrEventHandler`; the only new event-to-audio.cpp logic.
- `wyoming_audiocpp_asr/server.py` — new Wyoming TCP server (the default entry point; `asr_server.py` is kept).
- `wyoming_audiocpp_asr/web_server.py` — new demo browser UI (reuses `asr_server.create_app`).
- `wyoming_audiocpp_asr/__main__.py` — CLI entry; starts the Wyoming service and optionally the demo web server.
- `wyoming_audiocpp_asr/config.py` — `Config` gains `uri`/`model`/`language`/zeroconf/web-server fields.
- `wyoming_audiocpp_asr/asr_server.py` — existing Flask HTTP bridge; KEPT as the demo HTTP server, imported by `web_server.py`.

## Verification

### Unit tests

New file `wyoming_audiocpp_asr/tests/test_asr_handler.py`:
- `test_handle_transcribe` — feed `Transcribe(language="en").event()`, then `AudioStart`, `AudioChunk` (fake 16-bit 16 kHz mono bytes), `AudioStop`; assert `Transcript` event carries text and `language="en"`; assert connection returns `False` on disconnect.
- `test_handle_audio_stop_empty` — `AudioStop` with no audio → empty-string `Transcript`.
- `test_handle_describe` — `Describe` event → server sends `Info` with an `asr` program named `audio.cpp`.

New file `wyoming_audiocpp_asr/tests/test_web_server.py`:
- `test_index_get` — `GET /` returns 200 with an HTML page containing the word "Transcribe".
- `test_transcribe_post` — POST a multipart WAV file to `/api/speech-to-text`; assert the response contains the transcribed text.
- `test_status_get` — `GET /api/status` returns JSON with `"service": "wyoming-audiocpp-asr"`.
- `test_health_get` — `GET /health` returns `{"status": "ok"}`.

### End-to-end (new-behavior proof)

```bash
# In a terminal: start the Wyoming ASR service (mDNS opt-in via --zeroconf)
cd /workspaces/wyoming_audiocpp_asr
python -m wyoming_audiocpp_asr --uri tcp://127.0.0.1:55001 --zeroconf

# In another terminal: connect over the Wyoming TCP protocol and run a
# non-streaming transcription; audio.cpp must stream back a Transcript.
python - <<'PY'
import asyncio
from wyoming.server import AsyncTcpServer
from wyoming.asr import Transcribe, AudioStart, AudioChunk, AudioStop

async def main():
    client = AsyncTcpServer.connect("tcp://127.0.0.1:55001")
    await client.write_event(Transcribe(language="en").event())
    await client.write_event(AudioStart().event())
    await client.write_event(AudioChunk(audio=b"\x00\x00\x01\x00\x02\x00").event())
    await client.write_event(AudioStop().event())
    for ev in client.read_events():
        print(ev.type, ev.data)
    client.close()

asyncio.run(main())
PY
```

Expected observable output: `transcript {"text": "<word>", "language": "en"}` — proof the service speaks the Wyoming protocol, not Flask.

For the demo web server (requires `--web-server` and the `web` optional deps):

```bash
python -m wyoming_audiocpp_asr --uri tcp://127.0.0.1:55001 --web-server --web-server-host 127.0.0.1 --web-server-port 5001
```

Then `curl http://127.0.0.1:5001/` returns HTML, `curl http://127.0.0.1:5001/api/status` returns the service info, and a multipart POST to `/api/speech-to-text` with a WAV returns the transcript.

`pytest tests/` passes; `pip install -e .` succeeds with Flask installed (Flask is now an optional `web` extra, not a hard dependency).

## Assumptions & contingencies

- Home Assistant has the Wyoming integration (a TCP client that resolves `_wyoming._tcp.local.`); this is the standard OHF-Voice client, not something the bridge must provide.
- audio.cpp must be running and reachable at the configured URI for `transcribe()` to succeed.
- Port `55001` configurable via `--uri`; `--zeroconf` opt-in (disabled by default) so HA discovery is not advertised unless requested.
- The demo web server binds `127.0.0.1` by default; `--web-server-allow` restricts it further. If `--web-server-allow` lists no address, the server binds `0.0.0.0` (same as before) so a host-local demo works; a typo is caught at startup.
- If `--web-server` is given but the `web` optional dependencies are not installed, the process errors at startup (`--web-server requires the 'web' optional dependencies`) rather than after the Wyoming server has started.
