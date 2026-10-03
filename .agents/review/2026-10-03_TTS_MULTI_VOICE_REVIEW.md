# Code Review: `feat/multi_tts_voices`

**Date:** 2026-10-03  
**Scope:** 36 files, +1217/−763 lines  
**Verdict:** **request_changes**

The multi-voice TTS feature is well-structured overall. The config layering, voice selection, and HTTP endpoints are clean. However, there are a few issues that need addressing before merge.

---

## Findings

### 1. `params.py` — `coerce()` crashes on non-numeric string for number/slider params
**Severity:** major  
**File:** `wyoming_audiocpp_tts/params.py:35-36`

When a config.json `options` value is a non-numeric string (e.g. `"temperature": "high"`) and the param type is `number` or `slider`, `float(value)` raises an unhandled `ValueError`. The exception propagates to the outer `except Exception` handlers in both `tts_handler.py` and `tts_server.py`, producing a generic 502 / `AudioStop` with no clear diagnostic. A user typo in config.json should produce a readable validation error, not a crash.

**Suggested fix:** Wrap the coercion in a try/except and raise a `ValueError` with a clear message, or validate at config-load time in `Config.validate()`:

```python
def coerce(model: str, name: str, value: Any) -> Any:
    t = param_types(model).get(name)
    if t in ("number", "slider"):
        try:
            return float(value)
        except (TypeError, ValueError):
            raise ValueError(f"param {name!r} must be numeric, got {value!r}")
    ...
```

### 2. `web_server.py` — Duplicate `/api/voices` route is unreachable dead code
**Severity:** minor  
**File:** `wyoming_audiocpp_tts/web_server.py:108-115`

The base Flask app from `tts_server.create_app()` already registers a `/api/voices` route (endpoint `api_voices`). `make_tts_web_server()` then calls `flask_app.add_url_rule("/api/voices", endpoint=f"api_voices_{id(config)}", view_func=_api_voices)`, registering a second route for the same path. Flask serves the first matching rule, so `_api_voices` is unreachable dead code.

**Suggested fix:** Remove the `_api_voices` function and its `add_url_rule` call (lines 108–115).

### 3. `config.py` — Module docstring is stale
**Severity:** minor  
**File:** `wyoming_audiocpp_tts/config.py:1-9`

The module docstring still references the old single-voice config layering: *"then ``config.json`` with project settings and voice overrides as a ``tts_voice`` object plus per-scalar fields prefixed by ``tts_voice0_<field>``"*. This is no longer accurate — voices come only from the `tts_voices` list in config.json.

**Suggested fix:** Update the docstring to describe the new `tts_voices` list schema.

### 4. `tts_handler.py` — `_find_voice` silent fallback masks config errors
**Severity:** minor  
**File:** `wyoming_audiocpp_tts/tts_handler.py:117-123`

`_find_voice` falls back to the first voice when the name doesn't match any configured voice. This is a silent fallback that could mask configuration errors (e.g. a typo in the voice name from Home Assistant). A warning log would help debugging.

**Suggested fix:**
```python
def _find_voice(self, name: Optional[str]) -> "VoiceConfig":
    if name:
        for v in self.config.tts_voices:
            if v.voice_name == name:
                return v
        _LOGGER.warning("Voice %r not found; falling back to first voice", name)
    return self.config.tts_voices[0]
```

### 5. `VoiceSelector.tsx` — `OverridesPanel` is dead code
**Severity:** minor  
**File:** `wyoming_audiocpp_demo/src/components/VoiceSelector.tsx:98-106`

The `OverridesPanel` component returns `null`, making it dead code. It's rendered in the JSX (line 93) but does nothing.

**Suggested fix:** Remove the `OverridesPanel` function and its usage, or implement it if it's planned for future use.

### 6. `page.tsx` — Hardcoded port overrides duplicate `config.ts` defaults
**Severity:** minor  
**File:** `wyoming_audiocpp_demo/src/app/page.tsx:11-14`

The page hardcodes `ttsBase: "http://localhost:5001"` and `asrBase: "http://localhost:5000"` in the initial state, duplicating the values from `config.ts` defaults. This should use the `defaults` import to avoid drift.

**Suggested fix:**
```tsx
import { defaults } from "../lib/config";
// ...
const [overrides, setOverrides] = useState<Overrides>(defaults);
```

### 7. `config.example.json` — Shared config is confusing for two packages
**Severity:** info  
**File:** `config.example.json`

The config contains both ASR fields (`asr_model`, `asr_language`, `uri`) and TTS fields (`tts_voices`, `tts_web_server`). Each package reads only its own fields, but the shared file is a bit confusing. The TTS bridge has no `uri` field (it uses its own default `tcp://0.0.0.0:10200`).

This is acceptable since each package's `Config.from_dict` only reads the fields it needs, but worth documenting in a comment.

### 8. ASR `asr_language` default is hardcoded to `"da"`
**Severity:** info  
**File:** `wyoming_audiocpp_asr/config.py:84`

The ASR config has `asr_language: Optional[str] = DEFAULT_LANGUAGE` where `DEFAULT_LANGUAGE = "da"`. This means the language is always set to Danish by default. For a general-purpose bridge, this should probably be `None` (auto-detect) rather than a hardcoded language. However, this appears to be intentional for the project's use case (Danish Home Assistant setup), so it's acceptable.

---

## Summary

| Severity | Count |
|----------|-------|
| Critical | 0 |
| Major | 1 |
| Minor | 5 |
| Info | 2 |

The major finding (`coerce()` crash) should be fixed before merge. The minor findings are cleanup items that improve robustness and maintainability. The overall architecture is sound: the multi-voice config layering, voice selection fallback, and HTTP endpoints are well-designed.
