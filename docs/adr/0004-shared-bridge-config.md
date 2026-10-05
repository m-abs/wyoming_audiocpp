# Shared `BridgeConfig` base class in `wyoming_audiocpp_common`

The ASR and TTS bridges had ~80% identical config layering code: `from_args`, `_apply_env`, `_apply`, `validate` boilerplate, and endpoint URL construction. Each package maintained its own copy, leading to drift (TTS's `_apply_env` only handled `audiocpp_uri` while ASR's was generic) and duplicated validation logic.

**Decision:** Extract a `BridgeConfig` base class into a new `wyoming_audiocpp_common/` sibling package. It holds the shared fields (`audiocpp_uri`, `enable_zeroconf`), the layered resolution machinery (`from_args` → config.json → env → CLI), generic scalar env parsing, and an `endpoint(path)` method. `AsrConfig` and `TtsConfig` subclass it, adding their own fields, validation, and endpoint properties.

**Alternatives rejected:**
- *Duplication (status quo):* Two copies of the same layering code drift over time.
- *Mixins:* Awkward with dataclass field ordering and `fields()` iteration.
- *Composition:* Breaks the flat `config.audiocpp_uri` access pattern used throughout both packages.

**Consequences:** New import paths (`AsrConfig` / `TtsConfig` instead of `Config`); all ~20 test files updated; `pyproject.toml` unchanged (no new entry point, the common package is internal). Web server fields stay per-package with `asr_`/`tts_` prefixes per the shared-config.json design.
