# Code Review: `034a55b` — "implemented: .agents/plans/2026-09-29-WYOMING_AUDIOCPP_TTS_SALVAGE.md"

**Date:** 2026-10-02
**Mode:** Reviewing commit `034a55b`, 14 files, +1193/−178.
**Scope note:** all 14 changed files in scope; the new `tts_handler.py` / `server.py` /
`web_server.py` are the substance, with the CLI (`__main__.py`) and config layering around them.

## Verdict

The Wyoming TTS bridge is implemented correctly for the success path, faithfully mirrors
`wyoming-piper`, and is well tested (50 passed on Python 3.14). **Do not merge as-is:** one P1
import blocker plus a real resource-lifecycle defect and dead code. The single highest-leverage
fix — deleting the dead `_request_body` method and its two tests — clears the P1 and two of the
findings at once.

| Category | Status | Notes |
|---|---|---|
| Core handler / server | ✅ Correct (success path) | `Describe`→`Info`, `Synthesize`→streaming chunks, WAV sink |
| `tts_handler.py` import | 🔴 Broken on 3.11 | unimported `Dict`/`Any` in dead `_request_body` annotation |
| Stream lifecycle | 🔴 Leaky | no cleanup on upstream failure → WAV leak + client hang |
| Config layering | ✅ Correct | defaults → config.json → env → CLI; validated |
| Web server add-on | ✅ Correct | reuses Flask app; allow-list via `REMOTE_ADDR`; optional extra |
| Tests | ✅ Strong (on 3.14) | handler, e2e TCP `Describe`, web routes/allow-list — but masks P1 |
| Dev/infra files | ⚠️ Low-risk | env var, gitignore, launch.json; verified by direct read |

---

## Findings

### 🔴 1. `tts_handler.py` cannot be imported on Python 3.11 (declared minimum)
`tts_handler.py:198` — `_request_body(...) -> Dict[str, Any]`, but the module imports only
`TYPE_CHECKING, List, Optional` from `typing` and has **no** `from __future__ import annotations`
(unlike every other module in the package). On eager-evaluation versions the return annotation
is evaluated at class-definition time:

```
$ /usr/bin/python3.11  # identical def -> Dict[str, Any], Dict/Any unimported
NameError: name 'Dict' is not defined. Did you mean: 'dict'?
$ .venv/bin/python -c "import wyoming_audiocpp_tts.tts_handler"   # Python 3.14
OK (deferred annotation evaluation)
```

`pyproject.toml` declares `requires-python = ">=3.11"` and lists 3.11/3.12/3.13 classifiers, so
the bridge (TCP server, CLI entry point, all tests) is unusable on its declared minimum. **The
devcontainer masks this by running Python 3.14**, where CPython defers annotation evaluation —
which is why all 50 tests pass yet the supported-version import fails. This is the merge blocker.

### 🔴 2. `_handle_synthesize` leaks the WAV and omits `SynthesizeStop` on upstream failure
`tts_handler.py:147-161`. If `audiocpp_client.synthesize` raises (audio.cpp non-2xx via
`raise_for_status`), the exception propagates out of the `async for`, so the trailing
`write_event(SynthesizeStop())` and `_close_wav()` are skipped. The client's synthesize request
is left pending with no terminating event (hangs until timeout) and the `wave.Wave_write` handle
leaks (unbounded growth under repeated failures). Fix: wrap the stream + cleanup in `try/finally`
so both always run, regardless of how the stream ends.

### ⚠️ 3. `_request_body` is dead code with a latent `NameError`
`tts_handler.py:198-205`. Never called in production — `_handle_synthesize` calls
`audiocpp_client.synthesize` → `voice.request_body` directly; only two tests reference it. Its
body references unimported `DEFAULT_VOICE_MODEL` (defined in `config.py`, not imported here), so
even with the annotation fixed, a `None`-voice call raises `NameError`. It also duplicates
`VoiceConfig.request_body`. **Removing this method + its two tests clears finding #1 (the P1) and
this finding together** — it is the single highest-leverage change.

### ⚠️ 4. Four incoming-event handler branches are unreachable (protocol direction)
`tts_handler.py:80-92`. `handle_event` dispatches to `_handle_synthesize_start/_chunk/_stop/
_stopped`. Per the Wyoming TTS protocol the **server** emits `SynthesizeStart/Chunk/Stop` (via
`write_event` inside `_handle_synthesize`); the client only sends `Synthesize` (+ `Describe`).
The "client-driven" comments reflect a direction-of-flow misunderstanding, so these four branches
are dead. Either wire them to a real streaming-input flow or delete them.

### ℹ️ 5. Minor / observations
- **Dev/infra files** (`.devcontainer/compose.yml`, `.devcontainer/postCreate.sh`, `.gitignore`,
  `.vscode/launch.json`) were not independently reviewed — the assigned reviewer was mis-scoped to
  the core handler and returned an incoherent result. Verified by direct read; all low-risk:
  `compose.yml` adds `PYTHON_AUTO_VRUN=1`; `postCreate.sh` is a trailing-newline fix; `.gitignore`
  adds the external reference checkouts (`wyoming-piper/`, `wyoming-faster-whisper`); `launch.json`
  flips the **ASR** debug bind to `0.0.0.0:55599` (unrelated to TTS, harmless dev convenience). No
  blockers here.
- `pyproject.toml` correctly moves `flask`/`werkzeug` out of hard `dependencies` into the `web`
  extra; the default install no longer requires Flask.
- The e2e test binds a dedicated high port (`11231`) to avoid clashing with the default `10200`.

---

## What's done well
- The core handler faithfully mirrors `wyoming-piper`: `Describe` → service `Info`, `Synthesize`
  → `SynthesizeStart` + empty-text `SynthesizeChunk` stream + `SynthesizeStop`, WAV written on disk
  and relayed as bytes.
- Blocking `requests` synthesis is offloaded via `loop.run_in_executor`, so one slow audio.cpp call
  does not stall other clients on the loop.
- Config layering (defaults → `config.json` → env → CLI) is clean and validated; `uri` must parse
  as `tcp://host:port`, `web_server_port > 0` when enabled.
- The demo web server reuses the existing Flask app, binds the socket in the caller's thread (a
  port-in-use is a startup error, not a silent background death), and allow-lists on the real
  `REMOTE_ADDR` peer (never a forwarded header). Good.
- New e2e test starts a real `AsyncTcpServer` and answers a `Describe` over a raw socket — strong
  proof the service is a genuine Wyoming TCP service, not Flask.

## Test evidence
```
$ .venv/bin/python -m pytest wyoming_audiocpp_tts/tests/ -q
50 passed in 5.40s
```
All on Python 3.14 (venv). This is exactly why the P1 import blocker is masked: the suite passes
where the module imports, not where it must also work (3.11).

## Recommended fix order
1. `tts_handler.py` — delete dead `_request_body` + its two tests (clears findings #1 and #3; fixes
   the P1 import blocker).
2. `tts_handler.py` — wrap `_handle_synthesize` stream + cleanup in `try/finally` (#2).
3. `tts_handler.py` — wire or delete the four unreachable incoming-event handlers (#4).
