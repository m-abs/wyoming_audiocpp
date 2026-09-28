export type Overrides = {
  ttsBase: string;
  asrBase: string;
};

export const defaults: Overrides = {
  ttsBase: "http://localhost:11201",
  asrBase: "http://localhost:11301",
};

// Base URLs for the Wyoming Flask bridges and audio.cpp.
//
 // Both Flask bridges default to 0.0.0.0, so the playground must launch
 // them on distinct ports (TTS --port 11201, ASR --port 11301). audio.cpp
 // runs in the devcontainer on :8080 and is only needed for local curl checks.
export const config = {
  ttsBase: defaults.ttsBase,
  asrBase: defaults.asrBase,
  // Kept for reference; the bridges proxy to this.
  audiocppUri: "http://localhost:8080",
};

// Runtime overrides (loaded from localStorage). Enables testing the playground
// against non-local hosts without editing source.
const KEY = "audiocpp-playground.ports";
export function loadOverrides(): Overrides {
  if (typeof window === "undefined") return { ...defaults };
  try {
    const raw = window.localStorage.getItem(KEY);
    return raw ? { ...defaults, ...JSON.parse(raw) } : { ...defaults };
  } catch {
    return { ...defaults };
  }
}

export function saveOverrides(o: Overrides): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(KEY, JSON.stringify(o));
  } catch {
    /* ignore */
  }
}
