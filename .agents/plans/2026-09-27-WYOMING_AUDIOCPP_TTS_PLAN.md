# wyoming-audiocpp-tts-plan

## Context

Implement `wyoming_audiocpp_tts`: a Wyoming-compatible TTS service that wraps audio.cpp's `/v1/audio/speech` endpoint. Configurable via CLI and `config.json`, starting with omnivoice and danish. Supports multiple voices, each with a name, optional language, and extensible per-voice parameters (speed, instruct, seed, etc.) matching audio.cpp's request options. Update README with TTS info.

## Approach

### Phase 1: CLI entry point

- File: `wyoming_audiocpp_tts/__main__.py`
- Symbols: `main()`, `parse_args()`
- CLI flags:
  - `--config` (default: `config.json`) — path to config file
  - `--asr-model` (default: from config) — ASR model id (passthrough to existing ASR)
  - `--tts-voice0-model` (default: from config) — TTS voice model id (e.g., `omnivoice`)
  - `--tts-voice0-name` — voice name (e.g., `female`)
  - `--tts-voice0-language` (default: from config) — language hint (e.g., `da`)
  - `--tts-voice0-speed` (default: from config) — speaking rate multiplier (audio.cpp accepts `speed`)
  - `--tts-voice0-instruct` (default: from config) — instruction string (audio.cpp accepts `instruct`)
  - `--tts-voice0-extra-<key>` (default: from config) — arbitrary model option (e.g., `seed`, `response_format`)
- Behavior: parse CLI, build `Config` via `Config.from_args()`, start `TtsServer`.

### Phase 2: Config layer

- File: `wyoming_audiocpp_tts/config.py`
- Symbols: `Config` dataclass, `VoiceConfig` nested, `Config.from_args()`
- Fields:
  - `audiocpp_uri: str` — audio.cpp base URI (default: `http://localhost:8080`)
  - `asr_model: Optional[str]` — ASR model id (default: `hviske`)
  - `tts_voice: Optional[VoiceConfig]` — default TTS voice (optional; CLI flags override this)
- `VoiceConfig` nested dataclass:
  - `model: str` — TTS model id (e.g., `omnivoice`)
  - `name: Optional[str]` — voice name (e.g., `female`)
  - `language: Optional[str]` — language hint
  - `speed: Optional[float]` — speaking rate multiplier
  - `instruct: Optional[str]` — instruction string
  - `extra: Dict[str, Any]` — arbitrary model options (e.g., `seed`, `response_format`)
- Override rule: CLI flags `--tts-voiceN-*` override `tts_voice` if present; if `tts_voice` is absent, CLI must specify at least one voice.
- JSON schema for `config.json`:
  ```json
  {
    "audiocpp_uri": "http://localhost:8080",
    "asr_model": "hviske",
    "tts_voice": {
      "model": "omnivoice",
      "name": "female",
      "language": "da",
      "speed": 1.0,
      "instruct": "female, low pitch",
      "extra": {
        "seed": 1234
      }
    }
  }
  ```

### Phase 3: TTS client

- File: `wyoming_audiocpp_tts/audiocpp_client.py`
- Symbols: `TtsClient`, `post_text_to_speech(uri, voice_config)`
- HTTP request: `POST {uri}/v1/audio/speech`
  - Body JSON: `{"model": voice.model, "input": text}`
  - If `voice.name` is set, add `{"voice": voice.name}` to body.
  - If `voice.language` is set, add `{"language": voice.language}` to body.
  - If `voice.speed` is set, add `{"speed": voice.speed}` to body.
  - If `voice.instruct` is set, add `{"instruct": voice.instruct}` to body.
  - If `voice.extra` is set, extend `options` object with all key/value pairs from `voice.extra`.
- Response: `audio/wav` bytes.

### Phase 4: TTS server

- File: `wyoming_audiocpp_tts/tts_server.py`
- Symbols: `create_app(config)`
- Route: `POST /api/tts` — accept `{text}` JSON, call `TtsClient.post_text_to_speech()`, return `audio/wav` response.
- (Optional future) `POST /api/asr` — passthrough to existing ASR service via HTTP client.

### Phase 5: README updates

- File: `README.md`
- Add section "TTS" after ASR section.
- Document `wyoming-audiocpp-tts` install, config, CLI flags, and endpoint.
- Reference `config.example.json` with TTS example.

### Phase 6: Tests

- `wyoming_audiocpp_tts/tests/test_config.py` — config loading, override behavior, validation (audiocpp_uri required).
- `wyoming_audiocpp_tts/tests/test_client.py` — HTTP request shape matches audio.cpp TTS spec.
- `wyoming_audiocpp_tts/tests/test_server.py` — Flask app returns audio/wav.

## Critical files & anchors

- `wyoming_audiocpp_tts/__main__.py` — CLI entry, mirrors ASR CLI structure.
- `wyoming_audiocpp_tts/config.py` — `Config` dataclass, `VoiceConfig` nested with `extra: Dict`, `from_args()`.
- `wyoming_audiocpp_tts/audiocpp_client.py` — `TtsClient`, `post_text_to_speech()`.
- `wyoming_audiocpp_tts/tts_server.py` — `create_app()`, `POST /api/tts`.
- `README.md` — add TTS section after ASR.

## Verification

```bash
cd /workspaces/wyoming_audiocpp_tts
pip install -e . -q
python -m pytest tests/ -q
```

Manual:

```bash
# Boot TTS server
python -m wyoming_audiocpp_tts --host 127.0.0.1 --port 5056 --tts-voice0-model omnivoice --tts-voice0-name female --tts-voice0-language da --tts-voice0-speed 1.0

# Test endpoint (requires audio.cpp on http://localhost:8080)
curl -s http://127.0.0.1:5056/api/tts -H 'Content-Type: application/json' \
  -d '{"text": "Hjælp"}' -o out.wav
file out.wav  # should report audio/wav
```

## Assumptions & contingencies

- `config.json` may omit `tts_voice`; CLI must specify at least one `--tts-voiceN-*` flag if `tts_voice` is absent. If neither file nor CLI provide a voice, the server fails to start (exit code 2) with error message `"No TTS voice configured"`.
- audio.cpp TTS endpoint expects `model` field matching the model id in `server.json` (e.g., `omnivoice`). If the model is not loaded, audio.cpp returns 404/503; this service does not pre-check model loading.
- Per-voice params (`speed`, `instruct`, and any `extra` key) are optional; if omitted, audio.cpp uses model defaults.
- `extra` object in `VoiceConfig` is a plain dict that gets flattened into the request `options` object; key naming follows audio.cpp's API (e.g., `seed`, `response_format`, `voice_ref`).
