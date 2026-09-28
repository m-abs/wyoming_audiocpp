# React TTS/ASR Playground Interface

## Context

User wants a simple web interface to test audio.cpp's TTS and ASR capabilities via the Wyoming bridge servers. Two Flask servers exist:

- **TTS Server** (`wyoming_audiocpp_tts/tts_server.py`): `POST /api/tts` accepts `{text}` JSON, returns WAV audio (audio/wav). GET `/` returns service metadata.
- **ASR Server** (`wyoming_audiocpp_asr/asr_server.py`): `POST /api/speech-to-text` accepts multipart/form-data WAV file, optional `?language` query param, returns `{text, language}` JSON. GET `/api/info` returns available models.

Build a React/Next.js frontend to:
1. Text-to-speech: type text, select voice/config, play/download audio.
2. Speech-to-text: upload WAV, see transcribed text, download results.
3. View service info (models, voices).

## Approach

### Step 1: Initialize Next.js project with React

Command: `npx create-next-app@latest audiocpp-playground --typescript --tailwind --eslint --app --src-dir --no-import-alias`

Structure:
- `src/app/page.tsx` - main playground UI
- `src/components/` - reusable UI components
- `src/lib/api.ts` - API client functions

### Step 2: Create API client (`src/lib/api.ts`)

```typescript
const TTS_BASE = "/api/tts";
const ASR_BASE = "/api/speech-to-text";

// TTS: POST text → WAV stream
async function textToSpeech(text: string, voiceConfig?: VoiceConfig): Promise<Response> {
  const body = voiceConfig ? new URLSearchParams({ voice: JSON.stringify(voiceConfig) }) : undefined;
  const res = await fetch(TTS_BASE, { method: "POST", headers: { "Content-Type": "application/json" }, body });
  if (!res.ok) throw new Error(`TTS: ${res.statusText}`);
  return res;
}

// ASR: POST WAV file → { text, language }
async function speechToText(file: File, language?: string): Promise<{ text: string; language?: string }> {
  const formData = new FormData();
  formData.append("audio", file);
  const res = await fetch(`${ASR_BASE}?language=${language || ""}`, { method: "POST", body: formData });
  if (!res.ok) throw new Error(`ASR: ${res.statusText}`);
  return res.json();
}

// Service info
async function getTtsInfo(): Promise<any> { return fetch("/").then(r => r.json()); }
async function getAsrInfo(): Promise<any> { return fetch("/api/info").then(r => r.json()); }
```

### Step 3: Build UI components

#### Voice Selector Component (`src/components/VoiceSelector.tsx`)
- Input: text area for TTS input
- Select: voice model dropdown (populated from `/api/info`)
- Options: language, speed toggles
- Buttons: "Play", "Download WAV"

#### ASR Upload Component (`src/components/AsrUpload.tsx`)
- Input: file picker for WAV files
- Select: language dropdown (auto-detect or manual)
- Progress: upload status
- Display: transcribed text in textarea
- Button: "Download text"

#### Main Layout (`src/app/page.tsx`)
- Header: title, service status indicators
- Two-column layout:
  - Left: TTS interface (text input, voice config, play/download)
  - Right: ASR interface (file upload, language, transcribed text, download)
- Footer: API endpoint URLs, config info

### Step 4: Styling

Use Tailwind CSS for responsive layout:
- Flexbox/grid for two-column design
- Clean typography for text inputs and results
- Visual feedback for loading states
- Download buttons styled consistently

### Step 5: Audio playback

Browser native `<audio>` element for playing TTS output.

## Critical Files & Anchors

1. `src/lib/api.ts` - API client functions (new)
2. `src/components/VoiceSelector.tsx` - TTS UI controls (new)
3. `src/components/AsrUpload.tsx` - ASR file upload (new)
4. `src/app/page.tsx` - main layout and composition (new)
5. `src/app/layout.tsx` - Next.js root layout with Tailwind imports (existing, minimal change)

## Verification

1. **TTS flow**: Type "Hello world", click "Play" → browser audio plays WAV
2. **ASR flow**: Upload test.wav from `/test_data/`, click "Transcribe" → text appears in textarea
3. **Info endpoints**: Voice selector shows available models from ASR `/api/info`
4. **Download**: WAV file downloads with correct MIME type; text file downloads .txt

## Assumptions & Contigencies

- **Audio.cpp server reachable**: Assumes `http://localhost:8080` (audio.cpp) is running. Fallback: display error message with manual endpoint override option (text input field).
- **Flask servers reachable**: Assumes `http://localhost:5001` (TTS) and `http://localhost:5002` (ASR) are running. These are the Wyoming bridge defaults; if not, user must edit `src/config.ts` with correct URLs.
- **WAV format only**: ASR component shows .wav/.WAV in file picker accept types. If user selects other formats, browser rejects gracefully.
- **Single React app**: User requested React/Next.js; building one unified app instead of separate pages.
- **No backend for Next.js**: Frontend directly proxies to Flask servers. If CORS issues arise, add Next.js `next.config.js` with `headers` middleware or run Flask with `CORS` enabled.
