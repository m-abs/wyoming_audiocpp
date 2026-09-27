# wyoming-audiocpp-asr-plan

## Context

Implement `wyoming_audiocpp_asr`: a Wyoming-compatible ASR service that bridges Home Assistant / Rhasspy to audio.cpp's transcription models. Configurable via CLI and `config.json`, starting with hviske and danish. Update README with ASR info and `config.example.json`.

## Approach

### Phase 1: Config layer

- File: `wyoming_audiocpp_asr/config.py`
- Symbols: `Config` dataclass, `Config.from_args()`
- Fields:
  - `audiocpp_uri: str` — audio.cpp base URI (default: `http://localhost:8080`)
  - `model: str` — ASR model id (default: `hviske`)
  - `language: Optional[str]` — language hint (default: `da`)
- `to_dict()` returns `{"audiocpp_uri": ..., "model": ..., "language": ...}`.
- Validation: `audiocpp_uri` and `model` required; scheme must be `http`/`https`.
- JSON schema for `config.json`:
  ```json
  {
    "audiocpp_uri": "http://localhost:8080",
    "model": "hviske",
    "language": "da"
  }
  ```

### Phase 2: HTTP client

- File: `wyoming_audiocpp_asr/audiocpp_client.py`
- Symbols: `transcribe(endpoint, wav_bytes, model, language, *, timeout)`
- HTTP request: `POST {endpoint}` (multipart/form-data)
  - `files`: `{"file": ("audio.wav", "audio/wav", "audio/wav")}`
  - `data`: `{"model": model}` plus `{"language": language}` if set.
- Response: parsed JSON dict `{"text": ..., "language": ...}`.

### Phase 3: Server

- File: `wyoming_audiocpp_asr/asr_server.py`
- Symbols: `create_app(config)`
- Routes:
  - `POST /api/speech-to-text` — accept WAV body, transcribe via client, return `{"text": ..., "language": ...}`.
  - `GET /api/info` — list ASR models available through audio.cpp.
- Error handling: `400` for empty body, `502` for audio.cpp errors.

### Phase 4: CLI entry point

- File: `wyoming_audiocpp_asr/__main__.py`
- Symbols: `main()`, `build_parser()`
- CLI flags:
  - `--config` (default: `config.json`)
  - `--audiocpp-uri` — audio.cpp base URI (default from config)
  - `--model` — ASR model id (default from config)
  - `--language` — language hint (default from config)
  - `--host` (default: `0.0.0.0`)
  - `--port` (default: `5000`)
  - `--log-level` (default: `INFO`)
- Behavior: parse CLI, build `Config` via `Config.from_args()`, start Flask app.

### Phase 5: Tests

- `wyoming_audiocpp_asr/tests/test_config.py` — config loading, override behavior, validation (audiocpp_uri and model required).
- `wyoming_audiocpp_asr/tests/test_client.py` — HTTP request shape matches audio.cpp transcription spec.
- `wyoming_audiocpp_asr/tests/test_bridge.py` — Flask app endpoints return correct shapes.
- `wyoming_audiocpp_asr/tests/synth_wav.py` — minimal WAV payload builder for tests.

### Phase 6: README updates

- File: `README.md`
- Add "How it works", "Install", "Configure", "Run", "Develop" sections.
- Reference `config.example.json`.

## Critical files & anchors

- `wyoming_audiocpp_asr/config.py` — `Config` dataclass, `from_args()`, validation.
- `wyoming_audiocpp_asr/audiocpp_client.py` — `transcribe()`, the only audio.cpp client.
- `wyoming_audiocpp_asr/asr_server.py` — `create_app()`, `POST /api/speech-to-text`, `GET /api/info`.
- `wyoming_audiocpp_asr/__main__.py` — CLI entry, `main()`, `build_parser()`.

## Verification

```bash
cd /workspaces/wyoming_audiocpp_asr
pip install -e . -q
python -m pytest tests/ -q
```

Manual:

```bash
# Boot ASR server
python -m wyoming_audiocpp_asr --host 127.0.0.1 --port 5055

# Test endpoint (requires audio.cpp on http://localhost:8080)
curl -s http://127.0.0.1:5055/api/info

curl -s http://127.0.0.1:5055/api/speech-to-text \
  -H 'Content-Type: audio/wav' --data-binary @test.wav
```

## Assumptions & contingencies

- audio.cpp transcription endpoint expects `model` field matching the model id in `server.json` (e.g., `hviske`). If the model is not loaded, audio.cpp returns 404/503; this service does not pre-check model loading.
- Per-request params (`language`) are optional; if omitted, audio.cpp uses model defaults.
- The service relies on the uploaded WAV being a well-formed 16-bit 16 kHz mono WAV (Wyoming ASR and audio.cpp prefer exactly that format).
