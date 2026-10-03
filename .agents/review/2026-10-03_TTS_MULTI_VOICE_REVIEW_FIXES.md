# Review Fixes: `feat/multi_tts_voices`

**Date:** 2026-10-03  
**Review:** `.agents/review/2026-10-03_TTS_MULTI_VOICE_REVIEW.md`

All actionable findings (1 major, 5 minor) resolved. Info-level findings (7, 8) accepted as-is.

---

## Fixes Applied

### 1. `params.py` — `coerce()` crash on non-numeric string (major)
**File:** `wyoming_audiocpp_tts/params.py:35-39`

Wrapped `float(value)` in a try/except that raises `ValueError` with a clear diagnostic message when the value is not numeric.

```python
if t in ("number", "slider"):
    try:
        return float(value)
    except (TypeError, ValueError):
        raise ValueError(f"param {name!r} must be numeric, got {value!r}")
```

### 2. `web_server.py` — Duplicate `/api/voices` route (minor)
**File:** `wyoming_audiocpp_tts/web_server.py`

Removed the `_api_voices` function and its `add_url_rule` call. The base app from `tts_server.create_app()` already serves `/api/voices`.

### 3. `config.py` — Stale module docstring (minor)
**File:** `wyoming_audiocpp_tts/config.py:1-9`

Updated the docstring to describe the `tts_voices` list schema instead of the old single-voice `tts_voice0_<field>` pattern.

### 4. `tts_handler.py` — `_find_voice` silent fallback (minor)
**File:** `wyoming_audiocpp_tts/tts_handler.py:123`

Added a `_LOGGER.warning` when the requested voice name doesn't match any configured voice, so typos from Home Assistant are visible in logs.

### 5. `VoiceSelector.tsx` — Dead `OverridesPanel` (minor)
**File:** `wyoming_audiocpp_demo/src/components/VoiceSelector.tsx`

Removed the `OverridesPanel` function (returned `null`), its JSX usage, and the now-unused `overrides`/`onChange` props. Also removed the unused `Overrides` type import.

### 6. `page.tsx` — Hardcoded port overrides (minor)
**File:** `wyoming_audiocpp_demo/src/app/page.tsx`

Replaced hardcoded `ttsBase`/`asrBase` values with the `defaults` import from `lib/config.ts`, eliminating drift risk.

---

## Additional Fixes (post-review)

### 7. CORS preflight — Bridges blocked cross-origin requests from the demo
**Files:** `wyoming_audiocpp_tts/tts_server.py`, `wyoming_audiocpp_asr/asr_server.py`

The existing `after_request` only set `Access-Control-Allow-Origin`. The browser's preflight for `POST` with `Content-Type: application/json` required `Access-Control-Allow-Methods` and `Access-Control-Allow-Headers`. Added a `before_request` handler that responds to OPTIONS with 200 + all three headers, and enhanced `after_request` to include the full set.

### 8. TTS voice description — Both voices showed identical label in Home Assistant
**File:** `wyoming_audiocpp_tts/tts_handler.py:104`

The description was `f"audio.cpp voice ({v.model})"` — identical for all voices sharing the same model. Changed to `f"{v.voice_name} ({v.model})"` so each voice is distinguishable (e.g. "female (omnivoice)" vs "male (omnivoice)"). Added a test asserting distinct descriptions for multi-voice configs.

### 9. Demo select — White text on white background in dark mode
**File:** `wyoming_audiocpp_demo/src/components/VoiceSelector.tsx`

The `<select>` had no explicit background/text color, so options rendered white-on-white in dark mode. Added `bg-white text-zinc-900 dark:bg-zinc-800 dark:text-zinc-100`.

### 10. Voice display format — Inconsistent between web server and demo
**Files:** `wyoming_audiocpp_tts/web_server.py`, `wyoming_audiocpp_demo/src/components/VoiceSelector.tsx`

The web server's HTML template showed only `v.name`; the demo showed `v.name (v.model)`. Both now show `"name (model)"` matching the HA `TtsVoice` format.

### 11. Demo TTS — No visible audio element, button mislabeled
**File:** `wyoming_audiocpp_demo/src/components/VoiceSelector.tsx`

Replaced the hidden programmatic `new Audio()` playback with a visible `<audio controls>` element. Renamed the button from "Play" to "Synthesize" and disabled it when the input is empty.

### 12. Demo buttons — Wrong cursor on hover
**Files:** `wyoming_audiocpp_demo/src/components/VoiceSelector.tsx`, `wyoming_audiocpp_demo/src/components/AsrUpload.tsx`

All buttons now use `cursor-pointer` when active and `disabled:cursor-not-allowed` when inactive.

---

## Verification

- TTS test suite: 53/53 passed
- ASR test suite: passed (excluding pre-existing infra-dependent client test)
- TypeScript compilation: clean (`npx tsc --noEmit`)
- `coerce()` smoke test: raises `ValueError("param 'guidance_scale' must be numeric, got 'high'")` for non-numeric input; passes valid values through
- CORS preflight: OPTIONS returns 200 with `Allow-Origin/Methods/Headers`
