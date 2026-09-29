# React TTS/ASR Playground Interface

## Context

User wants a simple web interface to test audio.cpp's TTS and ASR capabilities via the Wyoming bridge servers. Two Flask servers exist:

- **TTS Server** (`wyoming_audiocpp_tts/tts_server.py`): `POST /api/tts` accepts `{text}` JSON, returns WAV audio (`audio/wav`). `GET /` returns service metadata. Upstream audio.cpp errors return 502.
- **ASR Server** (`wyoming_audiocpp_asr/asr_server.py`): `POST /api/speech-to-text` accepts multipart/form-data WAV file (field name **`file`**, filename `audio.wav`, type `audio/wav`), optional `?language` and `?model` query params, returns `{text, language}` JSON. `GET /api/info` returns `{asr:[{name, attribution:{name,url}, installed, languages}]}`. Empty body returns 400; upstream errors return 502.

Both Flask servers bind `0.0.0.0` by default (overridable via `--host`/`--port` in each `__main__.py`). They share a host, so the playground launches them on distinct ports by default: TTS `--port 11201`, ASR `--port 11301`.

audio.cpp (OpenAI-compatible) runs in the devcontainer on `http://localhost:8080`. The Flask bridges default `audiocpp_uri=http://localhost:8080` (config.py). No frontend scaffolding exists — the playground is entirely new.

Build a React/Next.js frontend to:
1. Text-to-speech: type text, **play/download audio**. ⚠️ Runtime voice selection does NOT work through the bridge: the Flask `/api/tts` endpoint only reads `text` from the request body and forwards a **server-side** default `VoiceConfig` (`config.tts_voice`) to audio.cpp. There is no request body field for voice. The VoiceSelector dropdown can only show metadata from `GET /` (`tts_name`/`tts_model`); selecting a model has no runtime effect unless the Flask bridge is updated to read voice from the request.
2. Speech-to-text: upload WAV, see transcribed text, download results.
3. View service info (ASR models, TTS voice metadata).

## Approach

### Step 1: Initialize Next.js project with React

Command: `npx create-next-app@latest wyoming_audiocpp_demo --typescript --tailwind --eslint --app --src-dir --no-import-alias`

Structure:
- `src/app/page.tsx` - main playground UI
- `src/components/` - reusable UI components
- `src/lib/api.ts` - API client functions
- `src/lib/config.ts` - base URLs + override UI (new)

### Step 2: Create API client (`src/lib/api.ts`)

```typescript
// Wyoming bridge base paths. The Flask bridges live at the app root, so these
// are relative to the Next.js frontend origin.
const TTS_BASE = "/api/tts";
const ASR_BASE = "/api/speech-to-text";

// Voice config mirrors audio.cpp VoiceConfig. NOTE: the TTS bridge IGNORES this
// object — it only reads `text` and forwards a server-side default VoiceConfig.
// It is only used for metadata display. The ASR path below CAN forward per-request.
export type VoiceConfig = {
  model?: string; // audio.cpp model id
  name?: string;  // audio.cpp `voice`
  language?: string;
  speed?: number;
  instruct?: string;
  extra?: Record<string, unknown>;
};

// TTS: POST {text} ONLY → WAV stream. The bridge ignores any `voice` field.
async function textToSpeech(text: string): Promise<Response> {
  const res = await fetch(TTS_BASE, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ text }) });
  if (!res.ok) throw new Error(`TTS: ${res.statusText}`);
  return res;
}

// ASR: POST WAV (field `file`) → { text, language }.
async function speechToText(file: File, language?: string, model?: string): Promise<{ text: string; language?: string }> {
  const formData = new FormData();
  formData.append("file", file, { type: "audio/wav", filename: "audio.wav" }); // field name must be `file`
  const res = await fetch(`${ASR_BASE}${language ? `?language=${language}` : ""}${model ? `&model=${model}` : ""}`, { method: "POST", body: formData });
  if (!res.ok) throw new Error(`ASR: ${res.statusText}`);
  return res.json();
}

// Service info.
async function getTtsInfo(): Promise<any> { const r = await fetch("/"); return r.json(); }
async function getAsrInfo(): Promise<any> { const r = await fetch("/api/info"); return r.json(); }
```

### Step 3: Build UI components

#### Voice Selector Component (`src/components/VoiceSelector.tsx`)
- Populates the model dropdown from ASR `GET /api/info` → `asr[].name` (audio.cpp model ids).
- Select: model dropdown (ASR models), `name`/voice field.
- Options: language, speed toggles; speed and language only sent when non-null (mirrors `VoiceConfig.request_body`).
- Buttons: "Play", "Download WAV".
- ⚠️ Voice selection only displays metadata; does not affect the TTS output (bridge limitation). See Context caveat.

#### ASR Upload Component (`src/components/AsrUpload.tsx`)
- Input: file picker for WAV files (accept `.wav`/`.WAV`; audio.cpp only accepts WAV).
- Select: model + language dropdowns. Model default `hviske`, language default `da` (config.py defaults); language may be left empty for auto-detect.
- Progress: upload status.
- Display: transcribed text in textarea.
- Button: "Download text".
- Model dropdown populated from ASR `/api/info`.

#### Main Layout (`src/app/page.tsx`)
- Header: title, service status indicators.
- Two-column layout:
  - Left: TTS interface (text input, voice config, play/download)
  - Right: ASR interface (file upload, model/language, transcribed text, download)
- Footer: API endpoint URLs, config info.
- Config panel: editable base URLs for both bridges (TTS/ASR) and the audio.cpp override, persisted to `src/lib/config.ts` for manual testing on non-local hosts.

### Step 4: Styling

Use Tailwind CSS for responsive layout:
- Flexbox/grid for two-column design; collapses to stacked on narrow screens.
- Clean typography for text inputs and results.
- Visual feedback for loading states.
- Download buttons styled consistently.

### Step 5: Audio playback

Browser native `<audio>` element for playing TTS output.

## Critical Files & Anchors

1. `src/lib/api.ts` - API client functions (new)
2. `src/lib/config.ts` - base URLs + override UI (new)
3. `src/components/VoiceSelector.tsx` - TTS UI controls (new)
4. `src/components/AsrUpload.tsx` - ASR file upload (new)
5. `src/app/page.tsx` - main layout and composition (new)
6. `src/app/layout.tsx` - Next.js root layout with Tailwind imports (existing, minimal change)

## Verification

1. **TTS flow**: Type "Hello world", click "Play" → browser audio plays WAV
2. **ASR flow**: Upload test.wav from `/test_data/` (16-bit 16 kHz mono WAV), click "Transcribe" → text appears in textarea
3. **Info endpoints**: Voice/ASR selectors show models from ASR `/api/info` (`asr[].name`); TTS `/` shows voice metadata
4. **Download**: WAV file downloads with `audio/wav`; text file downloads as `.txt`
5. **Model/language**: ASR transcribe with selected model/language; audio.cpp rejects non-WAV at decode (graceful browser reject)

## Assumptions & Contingencies

- **audio.cpp reachable**: `http://localhost:8080` (audio.cpp container in devcontainer). Verified by Flask `audiocpp_uri` default.
 **Flask bridges reachable**: default `0.0.0.0`; playground launches them on distinct ports (TTS `--port 11201`, ASR `--port 11301`). If not, user edits base URLs in `src/lib/config.ts`.
- **WAV format only**: ASR picker restricts to `.wav`/`.WAV`. Other formats rejected by audio.cpp.
- **Single React app**: One unified app instead of separate pages.
- **No backend for Next.js**: Frontend proxies directly to Flask servers. If CORS arises, add Next.js `next.config.js` `headers` middleware or enable Flask `CORS`.

## Discrepancies vs. Draft Plan (corrected here)

1. **ASR multipart field name**: Draft used `formData.append("audio", file)`; source uses field **`file`** with filename `audio.wav`, type `audio/wav` (`wyoming_audiocpp_asr/audiocpp_client.py`).
2. **Flask ports**: Draft assumed 5001/5002; both servers default `--port 5000`. Now default `--port 11201` (TTS) / `11301` (ASR); playground base URLs in `src/lib/config.ts` match.
3. **ASR `/api/info` shape**: Draft implied a voice_model list; actual returns `{asr:[{name, attribution:{name,url}, installed, languages}]}`.
4. **TTS `/` shape**: `{name, tts_model, tts_name, asr_model}` (voice name in `tts_name`, model id in `tts_model`).
5. **ASR query params**: `?language` and optional `?model` (default model `hviske`, language `da` in config.py).
6. **TTS runtime voice**: Draft's `textToSpeech(text, voiceConfig)` sent a `voice` field; the bridge only reads `text` and uses a server-side default `VoiceConfig`, so per-request voice is not supported. The client must send `{text}` only.
