# Shared Bridge Config Refactor

## Goal

Extract the duplicated config layering code (~80% identical between `wyoming_audiocpp_asr/config.py` and `wyoming_audiocpp_tts/config.py`) into a new `wyoming_audiocpp_common` package with a `BridgeConfig` base class.

## Decisions (settled via grilling)

| Decision | Answer |
|---|---|
| Shared module | `wyoming_audiocpp_common/` sibling package |
| Inheritance | `AsrConfig(BridgeConfig)`, `TtsConfig(BridgeConfig)` |
| `_apply_env` | Generic scalar parsing in base, skips non-primitives |
| Web server fields | Per-package, prefixed (`asr_web_server_*` / `tts_web_server_*`) |
| `validate()` | Base checks `audiocpp_uri` scheme; subclasses call `super().validate()` |
| `parse_tcp_uri` | ASR-only |
| Endpoint helper | `BridgeConfig.endpoint(path)` method |
| Test migration | Clean cutover, all imports updated |
| ADR | `docs/adr/0004-shared-bridge-config.md` |

## Structure

### New: `wyoming_audiocpp_common/`

```
wyoming_audiocpp_common/
├── __init__.py          # docstring only
└── config.py            # BridgeConfig base class + _parse_env helpers
```

**`BridgeConfig` fields:**
- `audiocpp_uri: str = "http://localhost:8080"`
- `enable_zeroconf: bool = False`

**`BridgeConfig` methods:**
- `endpoint(path: str) -> str` — join base URI + path (strip trailing slash)
- `from_dict(data) -> Self` — iterate `fields(cls)`, set matching keys
- `_apply_env() -> Self` — generic `WYO_<FIELD>` parsing, skips non-primitives
- `_apply(overrides) -> Self` — set non-None overrides
- `from_args(config_path, **overrides) -> Self` — config.json → env → CLI
- `validate()` — check `audiocpp_uri` scheme is http/https

**`_parse_env` helpers** (module-level):
- `_parse_bool(value) -> bool`
- `_parse_int(value) -> int`
- `_parse_env(type_str, value) -> Any` — dispatch by type annotation

### Refactored: `wyoming_audiocpp_asr/config.py`

```python
class AsrConfig(BridgeConfig):
    asr_model: str = "hviske"
    asr_language: Union[str, List[str]] = "da"
    asr_uri: str = "tcp://0.0.0.0:11301"
    asr_web_server: bool = False
    asr_web_server_host: str = "127.0.0.1"
    asr_web_server_port: int = 5000
    asr_web_server_allow: Optional[List[str]] = None

    @property
    def transcription_endpoint(self) -> str: ...

    def parse_tcp_uri(self) -> tuple[str, int]: ...

    def validate(self) -> None: ...  # super().validate() + ASR checks
```

### Refactored: `wyoming_audiocpp_tts/config.py`

```python
class TtsConfig(BridgeConfig):
    tts_voices: List[VoiceConfig] = field(default_factory=lambda: [VoiceConfig()])
    tts_uri: str = "tcp://0.0.0.0:11201"
    tts_web_server: bool = False
    tts_web_server_host: str = "127.0.0.1"
    tts_web_server_port: int = 5001
    tts_web_server_allow: Optional[List[str]] = None

    @property
    def tts_endpoint(self) -> str: ...

    def validate(self) -> None: ...  # super().validate() + TTS checks
```

`VoiceConfig` stays in `wyoming_audiocpp_tts/config.py` (TTS-specific).

## Import changes

All `from .config import Config` → `from .config import AsrConfig` / `TtsConfig`.
Test files that test the shared layering import from `wyoming_audiocpp_common.config`.

## Files touched

- **New:** `wyoming_audiocpp_common/__init__.py`, `wyoming_audiocpp_common/config.py`
- **Rewritten:** `wyoming_audiocpp_asr/config.py`, `wyoming_audiocpp_tts/config.py`
- **Updated imports:** `__main__.py`, `server.py`, `asr_handler.py`, `tts_handler.py`, `asr_server.py`, `tts_server.py`, `web_server.py` (both packages)
- **Updated tests:** all test files in both packages (~20 files)
- **New ADR:** `docs/adr/0004-shared-bridge-config.md`

## Verification

1. `.venv/bin/python -m pytest` — full suite passes
2. `.venv/bin/python -c "from wyoming_audiocpp_asr.config import AsrConfig; from wyoming_audiocpp_tts.config import TtsConfig"` — imports work
3. No remaining references to old `Config` class name in either package
