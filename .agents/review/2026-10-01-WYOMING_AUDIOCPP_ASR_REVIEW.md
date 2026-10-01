# Code Review: `9f9b23f` — "feat: missing Wyoming ASR implementation"

**Date:** 2026-10-01
**Mode:** Reviewing commit `9f9b23f` (parent `9f9b23f~1`), 18 files, +1242/−114.
**Scope note:** untracked `wyoming_audiocpp_tts/tts_handler.py` is out of scope for this
commit and was ignored, per instruction.

## Verdict

The core ASR implementation is sound, correctly mirrors the Wyoming ASR contract, and is
well tested (44 passed / 6 skipped locally; skips are the audio.cpp-dependent e2e tests).
**Do not merge as-is:** two real defects — a broken `.vscode/launch.json` debug config and
a stale, port-inconsistent demo default. Both are small fixes.

| Category | Status | Notes |
|---|---|---|
| Core handler / server | ✅ Correct | Event dispatch, in-memory WAV, Error surfacing, non-streaming |
| Config layering | ✅ Correct | defaults → config.json → `WYO_*` env → CLI; validated |
| Web server add-on | ✅ Correct | Reuses Flask app; bind-in-caller-thread; allow-list via `REMOTE_ADDR` |
| Tests | ✅ Strong | Handler protocol, config env, web endpoints, e2e TCP transcribe |
| `asr_handler.py` annotations | ⚠️ Latent | `Optional` used (L62–64) but not imported — breaks `get_type_hints`/mypy |
| `.vscode/launch.json` | 🔴 Broken | Uses removed `--host`/`--port` flags; fails to launch |
| Demo `config.ts` default | 🔴 Stale | `asrBase` → `55599`; every real surface uses `11301` |
| README | ⚠️ Pre-existing | Malformed code fence (not introduced by this commit) |

---

## Findings

### 🔴 1. `.vscode/launch.json` "Wyoming ASR" no longer launches
The commit bumps the port (`11301`→`55599`) but leaves the **old** flag set. The new CLI
(`__main__.py`) has **no** `--host`/`--port` — it is `--uri tcp://host:port`. Verified:

```
$ python -m wyoming_audiocpp_asr --host 127.0.0.1 --port 55599 --audiocpp-uri http://audio.cpp:8080
wyoming-audiocpp-asr: error: unrecognized arguments: --host 127.0.0.1 --port 55599
```

The "Wyoming ASR" debug config fails before the server starts. Fix:
```json
"args": ["--uri", "tcp://127.0.0.1:55001",
         "--web-server", "--web-server-port", "55599",   // only if the demo UI is wanted
         "--audiocpp-uri", "http://audio.cpp:8080"]
```
(Pick the port deliberately; see #2 — `55599` matches nothing else in the repo.)

### 🔴 2. Demo `config.ts` default port is inconsistent with every real ASR surface
`wyoming_audiocpp_demo/src/lib/config.ts` line 8 was changed to:
```ts
asrBase: "http://localhost:55599",
```
but every *live* ASR HTTP surface in the demo uses **`11301`**:
- `src/app/page.tsx:15` — initial `overrides.asrBase` = `11301` (what the UI actually fetches)
- `src/components/AsrUpload.tsx:154` and `VoiceSelector.tsx:201` — reset buttons → `11301`
- `tests/smoke.py:68`, `tests/mock_runner.py:40`, `tests/launch_real.py:28` — all `11301`

`config.ts`'s `defaults` is consumed only by the **dead** `api.ts` functions
(`textToSpeech`/`speechToText` are never called by any component — verified by grep). So
this is not a live break, but the new `55599` default:
- contradicts the stale comment three lines above it ("ASR --port 11301");
- is a latent landmine the moment `api.ts` is wired up (it would hit a dead port);
- `55599` is not a port any bridge binds.

Fix: revert `asrBase` to `http://localhost:11301` (and fix the comment), or — if `55599`
is intentional — update `page.tsx`, the two reset buttons, and the test harness to match.
Given the whole demo is standardized on `11301`, reverting is the correct, minimal change.

### ⚠️ 3. `--zeroconf` missing-dep path is not guarded (unlike `--web-server`)
`__main__.py` wraps the `--web-server` import in `try/except ImportError` → clean
`parser.error("--web-server requires the 'web' optional dependencies …")`. There is no
equivalent guard for `--zeroconf`. `server.py::_register_zeroconf` does
`from wyoming.zeroconf import HomeAssistantZeroconf` inside `asyncio.run(...)`, so a
missing `zeroconf` extra surfaces as an unhandled traceback:

```
$ python -m wyoming_audiocpp_asr --uri tcp://127.0.0.1:55999 --zeroconf
  (with zeroconf extra not installed)
pip install zeroconf
EXC: ModuleNotFoundError No module named 'zeroconf.asyncio'; 'zeroconf' is not a package
```

The help text and README both promise `--zeroconf` "requires the `zeroconf` extra",
implying graceful handling. Fix: probe the import in `__main__` (before starting the
server) and `parser.error`, mirroring the web-server path.

### ⚠️ 4. README malformed code fence (pre-existing, not a regression)
`README.md` lines ~196–200:
````
```bash
pytest -q tests/test_e2e_bridges.py
```
AUDIOCPP_URI=http://audio.cpp:8080 pytest -q tests/test_e2e_bridges.py
```
The `AUDIOCPP_URI=…` line sits outside the code fence (fence closed before it, then a stray
closing ` ``` `). This is present in the parent commit, so it is not introduced by this
change — but the commit touched the README heavily and it is a trivial drive-by fix.

### ⚠️ 5. `asr_server.fetch_programs` no longer reflects live audio.cpp models
The Flask `/api/info` handler previously did a live `requests.get(.../v1/models)`; the commit
replaces it with `build_asr_info(config).to_dict()`, which returns the **static** configured
single model (`config.model`). Consequence: `GET /api/info` always reports one model,
regardless of what audio.cpp actually has installed. This is consistent with the bridge's
single-model, non-streaming design and makes the demo's model list deterministic, but it is a
behavior change to the public HTTP contract — worth a line in the changelog/README so
consumers don't expect a live model list. (The old code had a latent bug anyway: it built
`asr_models` but returned the static dict regardless.)

### ⚠️ 6. `Optional` used but not imported in `asr_handler.py`
Lines 62–64 annotate instance attributes as `Optional[str]`, `Optional[wave.Wave_write]`,
and `Optional[io.BytesIO]`, but the module never imports `Optional` (it imports only
`TYPE_CHECKING` from `typing`, and has `from __future__ import annotations`). It does not
crash at runtime — attribute annotations are never evaluated — but it is a latent defect:

```python
>>> typing.get_type_hints(AudioCppAsrEventHandler.__init__)
NameError: name 'Config' is not defined   # then, with Config supplied: 'Optional'
```

Any tooling that resolves the hints (mypy, `get_type_hints`, sphinx autotype) will fail.
Fix: `from typing import Optional` (one line).

### ℹ️ 7. Minor / observations
- `config.ts` line 13–15 comment is stale: it says "Both Flask bridges … ASR --port 11301",
  but the ASR bridge is now a Wyoming **TCP** service (`--uri`), not a Flask HTTP `--port`.
- `tests/launch_real.py:63` derives the TCP port as `asr_port - 11301 + 55001` (a magic
  offset). Correct for the default (`11301→55001`) and it shifts coherently for custom
  `asr_port`, but the coupling is undocumented magic; a one-line comment or named constant
  would help. (It has a short comment, so acceptable.)
- `asr_handler.py::AudioCppAsrEventHandler` accumulates audio in per-connection instance
  state; Wyoming builds one handler per connection, so isolation is correct. `disconnect()`
  releases the WAV buffer mid-utterance (leak-safe, tested).
- `AudioStop` with no audio short-circuits to an empty `Transcript` without calling
  audio.cpp (tested); upstream failure is relayed as a Wyoming `Error` event (tested).
- `web_server.run_web_server` binds the socket in the caller's thread so a port-in-use is a
  startup error, not a silent background-thread death; `AllowListMiddleware` keys on
  `REMOTE_ADDR` (the real peer), never a forwarded header, and handles IPv4-mapped-IPv6
  peers. Good.
- `Config.validate()` now enforces `uri` parses as `tcp://host:port`, so a bad `--uri`
  fails at startup. `web_server_port > 0` is enforced when `web_server` is set. Good.

---

## What's done well
- The core handler faithfully mirrors `wyoming-faster-whisper`'s `DispatchEventHandler`:
  `Transcribe`/`AudioStart`/`AudioChunk`/`AudioStop` → single `Transcript` → disconnect.
  `Describe` returns service `Info`.
- Blocking `requests` transcription is offloaded via `asyncio.to_thread`, so one slow
  audio.cpp call does not stall other clients on the loop.
- Config layering (defaults → `config.json` → `WYO_*` env → CLI) is clean, the `None`
  "leave unset" semantics are preserved, and env parsing is covered by tests
  (`test_from_args_env_var_applied`, `test_from_args_cli_beats_env`).
- `flask`/`werkzeug` moved out of hard `dependencies` into the `web` extra, and `zeroconf`
  into its own extra — the default install is lighter and correct.
- New `test_asr_wyoming_tcp_transcribe` exercises the real Wyoming TCP protocol end-to-end
  (stripping the 44-byte WAV header, verified) — strong proof the service is a genuine
  Wyoming TCP service, not Flask.

## Test evidence
```
$ pytest wyoming_audiocpp_asr/tests/ tests/ -q
44 passed, 6 skipped in 1.8s
```
The 6 skips are the `happy_servers` e2e tests, skipped because audio.cpp is unreachable in
this environment (`happy_servers` calls `pytest.skip("audio.cpp unreachable")`) — the
intended behavior, not a masked failure.

## Recommended fix order
1. `.vscode/launch.json` — switch to `--uri` (finding #1).
2. `config.ts` — revert `asrBase` to `11301` + fix the stale comment (findings #2, #7).
3. `__main__.py` — guard `--zeroconf` import like `--web-server` (finding #3).
4. `asr_handler.py` — add `from typing import Optional` (finding #6).
5. Drive-by: README code fence (finding #4).
