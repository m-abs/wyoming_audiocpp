# TTS Multi-Voice Configuration Plan

## Context

The `wyoming_audiocpp_tts` bridge is strictly single-voice: one `VoiceConfig` slot (`config.tts_voice`), all CLI flags hardcode index 0 (`--tts-voice0-*`), the `Describe` event advertises exactly one voice, and the `Synthesize` handler ignores Wyoming's optional `event.voice` field. The user needs:

1. **Multiple voices** — a TTS service exposes several named voices; each is an audio.cpp model, and the same model may be used in multiple voices with different parameters.
2. **Future-proof, correctly-typed parameters** — every audio.cpp model takes different request options (e.g. omnivoice's `instruct`, which `references/audio.cpp/model_specs/omnivoice.json` omits but `references/audio.cpp/webui/configs/model_params.json` declares with a type). The bridge must forward arbitrary per-model options **with the right JSON types** (numbers as numbers, not strings) without a code change per model.
3. **Config.json only — no CLI for model/voice params.** Model and voice configuration lives in a single shared `config.json`; the model/voice CLI flags are dropped. Operational flags (`--uri`, `--audiocpp-uri`, `--web-server`, …) remain.
4. **One shared `config.json`** usable by BOTH the ASR and TTS bridges without change (Docker convenience). Ambiguous fields are prefixed `asr_` / `tts_`.
5. **A new example JSON that works with the devcontainer VSCode launchers** (`.vscode/launch.json`).
6. **Both web demos updated** — the small Flask demo in `wyoming_audiocpp_tts/` and the bigger Next.js 16 playground in `wyoming_audiocpp_demo/`.

Intended end state: a flat shared `config.json` with `audiocpp_uri` (common), `asr_model`/`asr_language` (ASR), and `tts_voices` (a list). Each voice carries a free-form `options` dict; when building the wire body, each option value is coerced to its declared type from audio.cpp's `model_params.json`. The Wyoming handler selects a voice by name per request. Both demos show a voice-name dropdown and send the selected name. The VSCode launchers point at the shared example JSON.

## Approach

Order matters: steps 1–4 build the backend; step 5 depends on it; steps 6–7 update the demos, example JSON, and launchers. Existing tests that assert the old single-voice schema are updated in place (no new test files). Run the suite after each step.

### Step 1 — Shared config schema: rename ASR fields with `asr_` prefix, drop their CLI flags

Goal: a flat `config.json` where each bridge reads only its own keys, unambiguous via prefixes. ASR's top-level `model`/`language` collide in meaning with TTS voice models, so they become `asr_model`/`asr_language`. Their CLI flags are dropped (config.json is the source of truth); env vars still override them.

**`wyoming_audiocpp_asr/config.py`:**
- Field `model: str = DEFAULT_MODEL` → `asr_model: str = DEFAULT_MODEL`.
- Field `language: Optional[str] = DEFAULT_LANGUAGE` → `asr_language: Optional[str] = DEFAULT_LANGUAGE`.
- `to_dict()`: keys `"model"`→`"asr_model"`, `"language"`→`"asr_language"`.
- `validate()`: `if not self.model` → `if not self.asr_model`.
- `from_dict()` and `_apply_env()` are generic loops over `fields(cls)`, so they pick up the new names automatically (env vars become `WYO_ASR_MODEL` / `WYO_ASR_LANGUAGE`). No other change.

**`wyoming_audiocpp_asr/__main__.py`:**
- **Delete** the `--model` and `--language` flags.
- `main()`: remove `model=args.model` and `language=args.language` from the `Config.from_args(...)` call (they now come only from config.json / env).

ASR's `from_dict` already ignores unknown keys, so a file containing `tts_voices` is tolerated with no further change.

### Step 2 — Param-type coercion from audio.cpp's `model_params.json`

Goal: forward option values with the correct JSON types (numbers as numbers, bools as bools) so audio.cpp never receives a number-as-string. Types come from `references/audio.cpp/webui/configs/model_params.json`, which is keyed by model id and lists each param's `type` (`number`, `slider`, `bool`, `choice`, `text`).

**New file `wyoming_audiocpp_tts/params.py`:**
```python
"""Load audio.cpp model param types for wire-body coercion.

Types come from audio.cpp's webui ``model_params.json`` (keyed by model id,
each entry a list of {name, type, ...}). The reference copy under
``references/`` is freshest in the devcontainer; the bundled copy is the
reliable fallback for Docker where ``references/`` is absent.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

_REPO_ROOT = Path(__file__).resolve().parent.parent
_REFERENCE = _REPO_ROOT / "references/audio.cpp/webui/configs/model_params.json"
_BUNDLED = Path(__file__).resolve().parent / "params.json"


def _load() -> Dict[str, list]:
    for path in (_REFERENCE, _BUNDLED):
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    return {}


def param_types(model: str) -> Dict[str, str]:
    """Return {param_name: type} for a model; empty when the model is unknown."""
    entries = _load().get(model, [])
    return {e["name"]: e["type"] for e in entries if "name" in e and "type" in e}


def coerce(model: str, name: str, value: Any) -> Any:
    """Coerce a param value to its declared type; pass through when unknown."""
    t = param_types(model).get(name)
    if t in ("number", "slider"):
        return float(value)
    if t == "bool":
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return bool(value)
        return str(value).strip().lower() in ("true", "1", "yes")
    if t in ("text", "choice"):
        return str(value)
    return value  # unknown type: trust the config.json value as-is
```

**Copy `references/audio.cpp/webui/configs/model_params.json` to `wyoming_audiocpp_tts/params.json`** (the bundled fallback). This makes the bridge self-contained in Docker. The reference-first loader keeps it fresh in the devcontainer.

### Step 3 — TTS `VoiceConfig`: replace `instruct`+`extra` with a free-form `options` dict, coerced on send

Goal: future-proof parameters. Any model's request options go into `options`, forwarded verbatim to audio.cpp's `options` object. `instruct` and the old `extra` keys both lived in `options`; they collapse into one dict. Top-level scalars that map to top-level body fields (`language`, `speed`) stay first-class. Option values are coerced by type (Step 2) so numbers are never sent as strings.

**`wyoming_audiocpp_tts/config.py` — rewrite `VoiceConfig`:**
```python
@dataclass
class VoiceConfig:
    model: str = DEFAULT_VOICE_MODEL          # "omnivoice"
    name: Optional[str] = None                # voice id; defaults to model
    language: Optional[str] = None            # top-level body field
    speed: Optional[float] = None             # top-level body field
    options: Dict[str, Any] = field(default_factory=dict)  # verbatim -> audio.cpp "options"

    @property
    def voice_name(self) -> str:
        return self.name if self.name else self.model

    def request_body(self, input: str) -> Dict[str, Any]:
        from . import params
        body: Dict[str, Any] = {"model": self.model, "input": input}
        if self.language is not None:
            body["language"] = self.language
        if self.speed is not None:
            body["speed"] = float(self.speed)
        if self.options:
            body["options"] = {
                k: params.coerce(self.model, k, v) for k, v in self.options.items()
            }
        return body

    def to_dict(self) -> Dict[str, Any]:
        return {"model": self.model, "name": self.name,
                "language": self.language, "speed": self.speed,
                "options": self.options}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "VoiceConfig":
        result = cls()
        for key in ("model", "name", "language", "speed"):
            if key in data:
                setattr(result, key, data[key])
        if "options" in data:
            result.options = dict(data["options"])
        return result
```
Delete module constants `_SCALAR_FIELDS` and `_VOICE_FLAG_PREFIX` (no longer used). Keep `DEFAULT_VOICE_MODEL`, `DEFAULT_AUDIOCPP_URI`, `_SPEECH_ENDPOINT`.

### Step 4 — TTS `Config`: multi-voice list, config.json only (no voice CLI)

Goal: `tts_voices` is a list defined in config.json. No CLI flag for voices (the user dropped model/voice CLI args). Env vars cover top-level fields only (a list can't be set via env cleanly).

**`wyoming_audiocpp_tts/config.py` — rewrite `Config`:**
- Replace field `tts_voice: Optional[VoiceConfig] = None` with `tts_voices: List[VoiceConfig] = field(default_factory=lambda: [VoiceConfig()])` (one default omnivoice voice so it works out of the box).
- **Delete** the `asr_model` field (redundant; the demo gets ASR models from the ASR bridge's endpoint, not from TTS).
- `tts_endpoint` property: unchanged.
- Delete `_merge_voice` (single-voice merge no longer applies).
- `from_dict(data)`: read `data.get("tts_voices")`; if a non-empty list, `[VoiceConfig.from_dict(v) for v in ...]`, else `[VoiceConfig()]`. Also read `audiocpp_uri`. Return `cls(audiocpp_uri=..., tts_voices=...)`.
- `_apply_env()`: top-level only — `WYO_AUDIOPCPP_URI` → `audiocpp_uri`. No per-voice env vars.
- `from_args(config_path, **overrides)`: load config.json → `from_dict`; `_apply_env`; apply non-None top-level overrides via `setattr` if `hasattr`. (No voice override path — voices come only from config.json.) Then `validate()`.
- `validate()`: `if not self.tts_voices: raise ValueError("No TTS voices configured")`; for each voice `if not voice.model: raise ValueError("tts_voices[].model must be set")`; keep the `audiocpp_uri` scheme check and the `web_server_port > 0` check.

**`wyoming_audiocpp_tts/__main__.py`:**
- **Delete** `_add_voice_scalar_args` and `_add_voice_extra_args` (the `--tts-voice0-*` flags) and the `_voice_overrides` helper.
- `main()`: remove the `voice_overrides=...` argument from the `Config.from_args(...)` call.

### Step 5 — Per-request voice selection + Describe advertises all voices

Goal: Wyoming's `Synthesize.voice.name` selects a configured voice; unknown/absent names fall back to the first voice. `Describe` lists every voice.

**`wyoming_audiocpp_tts/tts_handler.py`:**
- Replace `_build_tts_info(voice) -> List[TtsVoice]` (single) with `_build_tts_info(voices: List[VoiceConfig]) -> List[TtsVoice]` returning one `TtsVoice` per voice: `name=v.voice_name`, `description=f"audio.cpp voice ({v.model})"`, `languages=[v.language] if v.language else ["en"]`, `attribution=Attribution(name="audio.cpp", url="https://github.com/0xShug0/audio.cpp")`, `installed=True`, `version=None`, `speakers=[TtsVoiceSpeaker(name=v.voice_name)]`. The `_handle_describe` call becomes `voices=self._build_tts_info(self.config.tts_voices)`.
- Add `_find_voice(self, name: Optional[str]) -> VoiceConfig`: if `name` matches a voice's `voice_name`, return it; else return `self.config.tts_voices[0]`.
- In the synthesize path, select the voice: `voice_name = synthesize.voice.name if synthesize.voice else None`; `voice = self._find_voice(voice_name)`; pass that `voice` (not `self.config.tts_voice`) to `audiocpp_client.synthesize(self.config.tts_endpoint, voice, text)`.

### Step 6 — Small demo (Flask) voice picker

Goal: browser picks a voice by name; the bridge selects it and synthesizes.

**`wyoming_audiocpp_tts/tts_server.py`:**
- `create_app(config)`: set `app.config["TTS_VOICES"] = config.tts_voices` (delete `app.config["TTS_VOICE"]`).
- Add a module-level `_find_voice(voices, name)` helper mirroring the handler's logic (return match by `voice_name`, else first).
- `POST /api/tts`: read `body.get("text")` (required) and `body.get("voice")` (a voice-name string). Select via `_find_voice(app.config["TTS_VOICES"], body.get("voice"))`; call `audiocpp_client.text_to_speech(app.config["TTS_ENDPOINT"], voice, text=text)`.
- Add `GET /api/voices` → `jsonify({"voices": [{"name": v.voice_name, "model": v.model} for v in app.config["TTS_VOICES"]]})`.
- `GET /`: return `{"name": SERVICE_NAME, "tts_voices": [v.voice_name for v in app.config["TTS_VOICES"]]}` (delete the old `tts_model`/`tts_name`).

**`wyoming_audiocpp_tts/web_server.py` — `_render_index()`:**
- Add a `<select id="voice">` dropdown. On load, `fetch('/api/voices')` and populate `<option value="<name>"><name></option>` for each voice (first option is the default).
- The `synthesize()` JS sends `body: JSON.stringify({text: text, voice: document.getElementById('voice').value})`.

### Step 7 — Big demo (Next.js 16) voice picker

Goal: browser fetches the TTS voices list and picks one by name; per-voice params are preconfigured server-side, so the UI no longer sets model/language/speed/instruct.

**`wyoming_audiocpp_demo/src/lib/api.ts`:**
- Delete the `VoiceConfig` type (the browser no longer sends a config object).
- Change `textToSpeech(text: string, voiceName?: string)` to send `{ text, voice: voiceName }` when `voiceName` is set, else `{ text }`. The wire field `voice` is now a voice-name string (not a JSON config).
- Add `loadVoices(ttsBase: string): Promise<{name: string; model: string}[]>` that fetches `${ttsBase}/api/voices` and returns the `voices` array (return `[]` on failure so the UI degrades gracefully).
- Keep `speechToText` and `loadModels` unchanged (they serve the ASR side).

**`wyoming_audiocpp_demo/src/components/VoiceSelector.tsx`:**
- Replace the `model`/`voice`/`language`/`speed`/`instruct` state and the `OverridesPanel` with a single `voiceName: string` state.
- Accept a `voices: {name; model}[]` prop (replacing the `models: string[]` prop). Render a `<select>` of voice names; default to the first voice.
- `play()` calls `api.textToSpeech(text, voiceName)`.
- Delete the `useMemo`/`overrides` param-building logic and the `OverridesPanel` component.

**`wyoming_audiocpp_demo/src/app/page.tsx`:**
- Add a `voices` state; in a `useEffect`, call `loadVoices(overrides.ttsBase)` and set it (degrade to `[]` on failure). Pass `voices={voices}` to `<VoiceSelector>`.
- The existing `loadModels`/ASR-models flow for `AsrUpload` stays.

### Step 8 — Shared example JSON + VSCode launchers

Goal: one example `config.json` that both bridges read without change, wired into the devcontainer launchers.

**`config.example.json`** — replace the ASR-only file with the shared schema (matching the launcher defaults):
```json
{
  "audiocpp_uri": "http://audio.cpp:8080",
  "asr_model": "hviske",
  "asr_language": "da",
  "tts_voices": [
    { "name": "default", "model": "omnivoice" },
    { "name": "female", "model": "omnivoice", "options": { "instruct": "female voice" } }
  ]
}
```

**`.vscode/launch.json`:**
- **Wyoming ASR** configuration: remove nothing (it has no model flags); add `"--config", "config.example.json"` to `args` (cwd is `/workspaces`, so the relative path resolves).
- **Wyoming TTS** configuration: delete the six `--tts-voice0-*` args; add `"--config", "config.example.json"` to `args`. Keep `--uri`, `--web-server`, `--web-server-host`, `--web-server-port`, `--audiocpp-uri`.

### Step 9 — Update bridge-launching scripts/tests (they used the dropped flags)

**`tests/test_e2e_bridges.py`:**
- ASR launch: replace `--model hviske` with `--config <shared example json>` (or a test fixture matching Step 8). Keep `--uri`, `--web-server`, `--audiocpp-uri`.
- TTS launch: replace the `--tts-voice0-*` flags **and** the stale `--host/--port` with `--config <shared example json>` + `--uri tcp://127.0.0.1:<port>` (the TTS bridge is a Wyoming TCP service taking `--uri`, not `--host/--port`). Keep `--audiocpp-uri`.

**`wyoming_audiocpp_demo/run_mock_bridges.sh`:**
- TTS lines: replace `--host 127.0.0.1 --port <p> --tts-voice0-*` with `--uri tcp://127.0.0.1:<p> --config config.example.json`. Keep `--audiocpp-uri`.
- ASR line: replace `--model hviske` with `--config config.example.json`. Keep `--uri`, `--web-server`, `--audiocpp-uri`.

## Critical files & anchors

- `wyoming_audiocpp_tts/config.py` — `VoiceConfig` (rewrite: `options` dict, `voice_name`, coerced `request_body`) and `Config` (`tts_voices` list, config.json-only). The merge points every other change depends on.
- `wyoming_audiocpp_tts/params.py` + `wyoming_audiocpp_tts/params.json` — new type-coercion module and bundled `model_params.json` copy (reference-first loader).
- `wyoming_audiocpp_tts/tts_handler.py` — `_build_tts_info` (now per-voice), new `_find_voice`, synthesize path selects by name.
- `wyoming_audiocpp_asr/config.py` + `__main__.py` — the `asr_` rename; dropped `--model`/`--language`; generic loops make env/`from_dict` follow automatically.
- `.vscode/launch.json` + `config.example.json` — the launcher↔example-JSON wiring that makes the devcontainer work out of the box.

## Verification

Prereqs: `.venv/bin/python` from repo root; audio.cpp reachable at the configured URI for live synthesis, otherwise the 502 path is exercised.

1. **Unit — config layering + typed options:** `.venv/bin/python -m pytest wyoming_audiocpp_tts/tests/test_config.py`. A config.json with `tts_voices: [{name: female, model: omnivoice, options: {instruct: "female voice", num_inference_steps: "32"}}]` resolves to a 2-voice list; `request_body("hi")` yields `{"model":"omnivoice","input":"hi","options":{"instruct":"female voice","num_inference_steps":32.0}}` — the string `"32"` is coerced to a number, and `instruct` stays a string (no top-level `instruct`).
2. **Unit — per-request selection:** `.venv/bin/python -m pytest wyoming_audiocpp_tts/tests/test_tts_handler.py`. A `Synthesize` with `voice.name="female"` selects the female voice; absent/unknown name falls back to the first voice. `Describe` returns one `TtsVoice` per configured voice (assert count == len(tts_voices), not 1).
3. **Wire — client body:** `.venv/bin/python -m pytest wyoming_audiocpp_tts/tests/test_client.py`. The POSTed JSON puts model-specific params under `options` with correct types (numbers as numbers), never as top-level keys.
4. **Shared config — both bridges read one file, no CLI:** write a temp `config.json` matching Step 8; run `.venv/bin/python -m wyoming_audiocpp_asr --config <file> --web-server` and `.venv/bin/python -m wyoming_audiocpp_tts --config <file> --web-server`. Confirm ASR picks up `asr_model`/`asr_language` and TTS picks up `tts_voices`, and neither errors on the other's keys. Confirm both reject `--model`/`--tts-voice0-*` (flags are gone).
5. **Small demo:** start the TTS bridge with `--web-server --config config.example.json`; `curl GET /api/voices` lists the configured voices; `curl POST /api/tts -d '{"text":"hej","voice":"female"}'` returns a WAV (RIFF) using the female voice's options.
6. **Big demo:** `cd wyoming_audiocpp_demo && npm install && npx playwright install chromium`; run `next dev --port 11000` with the bridges up; the TTS panel shows a voice dropdown populated from `/api/voices`; selecting a voice and clicking play synthesizes using that voice. Run `.venv/bin/python wyoming_audiocpp_demo/tests/smoke.py` (auto-falls back to mock bridges).
7. **VSCode launchers:** in the devcontainer, confirm the "Wyoming ASR" and "Wyoming TTS" launch configs start cleanly with `--config config.example.json` (no model/voice flags), loading the shared voices.
8. **Full suite:** `.venv/bin/python -m pytest` — the whole root + per-package suite passes with the updated assertions.

## Assumptions & contingencies

- **Browser picks a preconfigured voice by name; it does not set per-voice params at request time.** Params are baked into the voice definition (config.json). This matches "the same model can be used in multiple voices with different parameters." Request-time param overrides are a separate feature.
- **A voice with no `name` uses its `model` as its id** (`voice_name`). Two same-model unnamed voices are indistinguishable; the first wins selection. Documented behavior, not an error.
- **Model/voice params are config.json-only; no CLI.** Operational flags (`--uri`, `--audiocpp-uri`, `--web-server`, …) remain. Env vars still override top-level fields (`WYO_AUDIOPCPP_URI`, `WYO_ASR_MODEL`, `WYO_ASR_LANGUAGE`); a voice list has no env form.
- **Type coercion reads the reference `model_params.json` first, then the bundled copy.** In the devcontainer (references present) it uses the freshest types; in Docker (references absent) it uses `wyoming_audiocpp_tts/params.json`. If a model/param is in neither file, the value is passed through as-is (trusts the config.json type). **Contingency:** when audio.cpp adds new models/params, update the bundled `params.json` (copy from `references/audio.cpp/webui/configs/model_params.json`) so their types are coerced.
- **The e2e test and `run_mock_bridges.sh` are already stale** (they pass `--host/--port` to a TTS bridge that takes `--uri`, and use dropped model flags). Updating them to `--config` + `--uri` also fixes this pre-existing breakage. If the bridge's actual bind differs from what the test expects, adjust the test's port/URI to match.
- **ASR field rename is breaking** (`model`→`asr_model`, `language`→`asr_language`) and their CLI flags are dropped. No backward-compat alias (clean cutover). External callers using `--model`/`WYO_MODEL` move to config.json / `WYO_ASR_MODEL`.
- **audio.cpp validates `options` keys against the model spec.** The bridge forwards coerced `options` verbatim; if a model's spec lacks a param (e.g. omnivoice's `instruct` in `model_specs/omnivoice.json`), audio.cpp rejects it. That is an upstream spec gap, not a bridge concern — the bridge forwards whatever the user configured, with correct types.
