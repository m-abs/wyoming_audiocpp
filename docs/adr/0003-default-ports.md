# Default ports: 11301 (ASR) and 11201 (TTS)

The default Wyoming TCP bind ports were changed from 55001 (ASR) and 10200 (TTS) to **11301** and **11201**. The old ports matched the reference implementations (wyoming-faster-whisper, wyoming-piper) but are in ranges commonly used by other services. The 11xxx range reduces the chance of port conflicts on a shared host.

The config fields were also renamed from the ambiguous shared `uri` to per-service `asr_uri` and `tts_uri`, with matching CLI flags (`--asr-uri` / `--tts-uri`) and env vars (`WYO_ASR_URI` / `WYO_TTS_URI`). This is because a single `config.json` is shared between both services, and a bare `uri` field would apply the same port to both.
