# wyoming-audiocpp-tts-plan

## Context

`wyoming_audiocpp_tts` currently ships as a Flask HTTP server exposing REST endpoints (`POST /api/tts`, `GET /`). Home Assistant and Rhasspy do not use this REST surface — they use the Wyoming protocol: an `AsyncTcpServer` listening on a TCP port and advertising itself via mDNS `_wyoming._tcp.local.` discovery. The TTS bridge has no zeroconf registration and no Wyoming event protocol, so it is invisible to HA/Rhasspy.

End state: the TTS bridge becomes a real Wyoming service — `wyoming.AsyncTcpServer` over TCP with opt-in `HomeAssistantZeroconf` mDNS registration, an `AsyncEventHandler` that turns Wyoming TTS events into calls to audio.cpp, and a CLI that starts the TCP server by default. The existing Flask server (`tts_server.py`) is KEPT as an optional demo HTTP server, started only with `--web-server`, and a browser-facing demo UI (`web_server.py`) is added as a `--web-server` add-on (like `wyoming-piper`). Discovery reference: https://github.com/OHF-Voice/wyoming-piper.

## Approach

### Step 1: TTS event handler

**File**: `wyoming_audiocpp_tts/tts_handler.py` (new)

**Symbol**: `AudioCppTtsEventHandler(AsyncEventHandler)`.

**Methods** (mirrors `wyoming_piper`'s TTS event handling):

- `handle_event(self, event: Event) -> bool`:
  - `Synthesize.is_type(event.type)` → start synthesis loop: build a `tempfile.TemporaryDirectory()` for WAV output, open `wave.Wave_write`, send `wyoming.tts.SynthesizeStart` event, call `audiocpp_client.synthesize()` streaming the `text`/`voice`/`options`; for each streaming audio chunk write bytes to the WAV file and send `wyoming.tts.SynthesizeChunk(text="").event()` (the Wyoming TTS streaming protocol emits empty `text` chunks while streaming audio), return `True`.
  - `SynthesizeStop.is_type(event.type)` → close WAV, send `wyoming.tts.SynthesizeStop().event()`, return `True` (TTS stays connected briefly).
  - `SynthesizeStopped.is_type(event.type)` → close WAV, return `False` (disconnect after complete).
  - `Describe.is_type(event.type)` → send service-info event; reuse `build_tts_info()` (new) and `write_event`.
  - any other type → return `True`.

**Reuse**: `wyoming_audiocpp_tts/audiocpp_client.py::synthesize()` (unchanged), `wyoming_audiocpp_tts/config.py::Config` (unchanged), `wyoming.tts.Synthesize`, `wyoming.tts.SynthesizeChunk`, `wyoming.tts.SynthesizeStop`, `wyoming.tts.SynthesizeStart`.

**New helper**: `build_tts_info(config: Config, voices: list[Voice]) -> Info` returns `wyoming.info.Info(tts=[TtsProgram(name="audio.cpp", description="audio.cpp text-to-speech", installed=True, voices=[Voice(name=voice.name, description=..., format=voice.format, languages=voice.languages) for voice in voices])])` — mirrors `wyoming_piper`'s TTS info builder.

### Step 2: Wyoming TCP server (replaces Flask server as the default)

**File**: `wyoming_audiocpp_tts/server.py` (new; `tts_server.py` KEPT, not deleted).

**Symbols**:
- `create_handler(config: Config) -> AudioCppTtsEventHandler` → `return AudioCppTtsEventHandler(config)`.
- `create_tcp_server(config: Config)`:
  - `from wyoming.server import AsyncServer, AsyncTcpServer`
  - `from wyoming.zeroconf import HomeAssistantZeroconf`
  - `uri = config.uri` (parse host/port from the `tcp://host:port` string)
  - `server = AsyncServer.from_uri(uri)`
  - if not disabled: `assert isinstance(server, AsyncTcpServer); hass_zeroconf = HomeAssistantZeroconf(name=config.zeroconf_name or "wyoming-audiocpp-tts", port=server.port, host=server.host); asyncio.create_task(hass_zeroconf.register_server())`
  - `asyncio.run(server.run(partial(create_handler, config)))`

**Behavior**: no Flask import in `server.py` or `__main__.py`. `tts_server.py` (Flask) is kept verbatim and imported only by `web_server.py`/`__main__.py` when `--web-server` is given.

### Step 3: Demo web server (browser UI alongside the Wyoming service)

**File**: `wyoming_audiocpp_tts/web_server.py` (new).

**Symbols**:
- `make_tts_web_server(config: Config, flask_app: Flask) -> Flask` — reuses `tts_server.create_app(config)` (the existing Flask `/api/tts` and `/` endpoints, unchanged) and adds browser routes:
  - `GET /` → HTML form: a text area (text) and a "Synthesize" button. The form posts `{text}` JSON to `/api/tts`; the handler plays/downloads the returned `audio/wav`.
  - `GET /health` → `{"status": "ok"}` (mirrors `wyoming-piper`'s `/health`).
  - `GET /api/status` → `{"service": "wyoming-audiocpp-tts", "tts_model": config.voice.model, "tts_name": config.voice.name, "asr_model": config.asr_model}` (mirrors `wyoming-piper`'s `/api/status`).
- `run_web_server(flash_app: Flask, host: str, port: int) -> threading.Thread` — runs the Flask app in a daemon thread (reuse `wyoming_piper.web_server.run_web_server` pattern: bind the socket, `werkzeug.serving.make_server(..., fd=sock.fileno())`, log level `ERROR`, return thread).

**Behavior**: reuses `tts_server.create_app`'s existing CORS after-request hook; no new audio.cpp logic.

### Step 4: CLI entry point

**File**: `wyoming_audiocpp_tts/__main__.py` — replace the Flask `app.run(...)` invocation.

**CLI flags** (mirror `wyoming-piper --help`):
- `--uri` (required) — `tcp://host:port`, default `tcp://0.0.0.0:10200`.
- `--web-server` (optional `action="store_true"`) — run the demo browser web server in a background thread (requires the `web` optional dependencies: Flask + `werkzeug`).
- `--web-server-host` (optional, default `127.0.0.1`) — interface for the demo web server.
- `--web-server-port` (optional int, default `5001`) — port for the demo web server.
- `--web-server-allow` (optional `action="append"`) — restrict the demo web server to these IP addresses/CIDRs (repeatable), since the UI has no authentication.
- `--zeroconf` (optional `action="store_true"`) — register mDNS `_wyoming._tcp.local.` discovery as `<name>` (default: the `--uri` host or `wyoming-audiocpp-tts`).
- `--debug` / `--log-format` / `--version` — logging/version.

**Entry flow**: `args = parse_args()`, `logging.basicConfig(...)`, `server = AsyncServer.from_uri(args.uri)`, register zeroconf via `HomeAssistantZeroconf(name=args.zeroconf, port=server.port, host=server.host)` and `asyncio.create_task(...)` if set, then `asyncio.run(server.run(partial(start_handler, config_from_args)))`. If `args.web_server`, start `run_web_server(make_tts_web_server(config_from_args), args.web_server_host, args.web_server_port)` in a background thread BEFORE the Wyoming server (the UI only reads config, so it does not need the backend, and a missing dependency or an unavailable port should fail now rather than after the wait).

### Step 5: Config layer

**File**: `wyoming_audiocpp_tts/config.py` — add fields to `Config`:
- `uri: str = "tcp://0.0.0.0:10200"` — Wyoming TCP bind.
- `enable_zeroconf: bool = False` — whether to register mDNS discovery.
- `zeroconf_name: Optional[str] = None` — mDNS service name (defaults to the URI host, else `wyoming-audiocpp-tts`).
- `web_server: bool = False` — whether to also start the demo web server.
- `web_server_host: str = "127.0.0.1"`, `web_server_port: int = 5001`, `web_server_allow: Optional[List[str]] = None` — demo web server settings.

Keep the existing `tts_voice`, `asr_model`, `audiocpp_uri`, and per-voice fields (used by `tts_server.py`/`audiocpp_client.py`). The layered `Config.from_args()` precedence is CLI > env var `WYO_WHISPER_*` > `config.json` > default.

**`Config` validation**: add `web_server_port` must be > 0 if `web_server`; `uri` must parse as a `tcp://` host/port when starting the Wyoming service.

## Critical files & anchors

- `wyoming_audiocpp_tts/tts_handler.py` — new `AudioCppTtsEventHandler`; the only new event-to-audio.cpp logic.
- `wyoming_audiocpp_tts/server.py` — new Wyoming TCP server (the default entry point; `tts_server.py` is kept).
- `wyoming_audiocpp_tts/web_server.py` — new demo browser UI (reuses `tts_server.create_app`).
- `wyoming_audiocpp_tts/__main__.py` — CLI entry; starts the Wyoming service and optionally the demo web server.
- `wyoming_audiocpp_tts/config.py` — `Config` gains `uri`/voice fields/zeroconf/web-server fields.
- `wyoming_audiocpp_tts/tts_server.py` — existing Flask HTTP bridge; KEPT as the demo HTTP server, imported by `web_server.py`.

## Verification

### Unit tests

New file `wyoming_audiocpp_tts/tests/test_tts_handler.py`:
- `test_handle_synthesize_stream` — feed `Synthesize(text="Hello").event()`; assert `SynthesizeStart` then a `SynthesizeChunk` stream then `SynthesizeStop` are emitted; assert WAV file on disk is valid.
- `test_handle_describe` — `Describe` event → server sends `Info` with a `tts` program named `audio.cpp` listing voices.

New file `wyoming_audiocpp_tts/tests/test_web_server.py`:
- `test_index_get` — `GET /` returns 200 with an HTML page.
- `test_synthesize_post` — POST `{text}` JSON to `/api/tts`; assert the response is `audio/wav` (non-empty).
- `test_status_get` — `GET /api/status` returns JSON with `"service": "wyoming-audiocpp-tts"`.
- `test_health_get` — `GET /health` returns `{"status": "ok"}`.

### End-to-end (new-behavior proof)

```bash
# In a terminal: start the Wyoming TTS service (mDNS opt-in via --zeroconf)
cd /workspaces/wyoming_audiocpp_tts
python -m wyoming_audiocpp_tts --uri tcp://127.0.0.1:10201 --zeroconf

# In another terminal: connect over the Wyoming TCP protocol and synthesize;
# audio.cpp must stream back SynthesizeChunk audio events.
python - <<'PY'
import asyncio
from wyoming.server import AsyncTcpServer
from wyoming.tts import Synthesize

async def main():
    client = AsyncTcpServer.connect("tcp://127.0.0.1:10201")
    await client.write_event(Synthesize(text="Hello").event())
    while True:
        ev = client.read_event()
        print(ev.type, ev.data)
        if ev.type == "synthesize-stopped":
            client.close()
            break
asyncio.run(main())
PY
```

Expected observable output: `synthesize-start`, `synthesize-chunk {...}` (audio), `synthesize-stop`, `synthesize-stopped` — proof the service speaks the Wyoming TTS protocol, not Flask.

For the demo web server (requires `--web-server` and the `web` optional deps):

```bash
python -m wyoming_audiocpp_tts --uri tcp://127.0.0.1:10201 --web-server --web-server-host 127.0.0.1 --web-server-port 5001
```

Then `curl http://127.0.0.1:5001/` returns HTML, `curl http://127.0.0.1:5001/api/status` returns the service info, and a POST of `{text: "Hello"}` to `/api/tts` returns WAV audio.

`pytest tests/` passes; `pip install -e .` succeeds with Flask installed (Flask is now an optional `web` extra, not a hard dependency).

## Assumptions & contingencies

- Home Assistant has the Wyoming integration (a TCP client that resolves `_wyoming._tcp.local.`); this is the standard OHF-Voice client, not something the bridge must provide.
- audio.cpp must be running and reachable at the configured URI for `synthesize()` to succeed.
- Port `10201` configurable via `--uri`; `--zeroconf` opt-in (disabled by default) so HA discovery is not advertised unless requested.
- The demo web server binds `127.0.0.1` by default; `--web-server-allow` restricts it further. If `--web-server-allow` lists no address, the server binds `0.0.0.0`; a typo is caught at startup.
- If `--web-server` is given but the `web` optional dependencies are not installed, the process errors at startup (`--web-server requires the 'web' optional dependencies`) rather than after the Wyoming server has started.
- The demo web server ports (`5001` for TTS, `5000` for ASR) are configurable via `--web-server-port` to avoid conflicts with other services.
