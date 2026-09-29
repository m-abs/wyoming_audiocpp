import { config } from "./config";

// Wyoming bridge base paths. The Flask bridges live at the app root, so these
// are relative to the Next.js frontend origin.
const TTS_PATH = "/api/tts";
const ASR_PATH = "/api/speech-to-text";

// audio.cpp VoiceConfig shape. Mirrors the fields the TTS UI sends.
export type VoiceConfig = {
  model?: string; // audio.cpp model id (required upstream)
  name?: string; // audio.cpp `voice`
  language?: string;
  speed?: number;
  instruct?: string;
  extra?: Record<string, unknown>;
};

const getOrigin = (base: string) => {
  try {
    return new URL(base).origin;
  } catch {
    return "";
  }
};

// TTS: POST JSON {text}. Field is `text` (Wyoming), NOT audio.cpp's `input`.
// The optional `voice` field is a JSON-serialized audio.cpp VoiceConfig.
// NOTE: the real Flask bridge only reads `body.get("text")`; `voice` is passed
// straight through to audio.cpp.
async function textToSpeech(
  text: string,
  voiceConfig?: VoiceConfig,
): Promise<Response> {
  const o = getOrigin(config.ttsBase);
  const body = voiceConfig ? { text, voice: JSON.stringify(voiceConfig) } : { text };
  const res = await fetch(`${o}${TTS_PATH}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`TTS: ${res.statusText}`);
  return res;
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
  speechToText,
};
