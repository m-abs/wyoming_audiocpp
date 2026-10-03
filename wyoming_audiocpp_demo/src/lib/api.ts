import { config } from "./config";

// Wyoming bridge base paths. The Flask bridges live at the app root, so these
// are relative to the Next.js frontend origin.
const TTS_PATH = "/api/tts";
const VOICES_PATH = "/api/voices";
const ASR_PATH = "/api/speech-to-text";

const getOrigin = (base: string) => {
  try {
    return new URL(base).origin;
  } catch {
    return "";
  }
};

// TTS: POST JSON {text, voice?}. `voice` is a voice-name string selected
// server-side from the configured voices.
async function textToSpeech(
  text: string,
  voiceName?: string,
): Promise<Response> {
  const o = getOrigin(config.ttsBase);
  const body = voiceName ? { text, voice: voiceName } : { text };
  const res = await fetch(`${o}${TTS_PATH}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`TTS: ${res.statusText}`);
  return res;
}

// Voices: GET /api/voices → { voices: [{name, model}] }.
async function getVoices(): Promise<{ name: string; model: string }[]> {
  const o = getOrigin(config.ttsBase);
  const res = await fetch(`${o}${VOICES_PATH}`);
  if (!res.ok) throw new Error(`Voices: ${res.statusText}`);
  const data = await res.json();
  return data.voices;
}

// ASR: POST WAV (multipart field `file`, filename audio.wav, type audio/wav) → { text, language }.
// Optional ?language and ?model query params.
async function speechToText(
  file: File,
  language?: string,
  model?: string,
): Promise<{ text: string; language?: string }> {
  const o = getOrigin(config.asrBase);
  const formData = new FormData();
  formData.append("file", file, "audio.wav"); // field name MUST be `file`
  const q = new URLSearchParams();
  if (language) q.set("language", language);
  if (model) q.set("model", model);
  const res = await fetch(`${o}${ASR_PATH}?${q.toString()}`, {
    method: "POST",
    body: formData,
  });
  if (!res.ok) throw new Error(`ASR: ${res.statusText}`);
  return res.json();
}

export const api = {
  textToSpeech,
  getVoices,
  speechToText,
};
