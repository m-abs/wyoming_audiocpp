export type Overrides = {
  ttsBase: string;
  asrBase: string;
};

export const defaults: Overrides = {
  ttsBase: "http://localhost:11201",
  asrBase: "http://localhost:11301",
};

// Base URLs for the demo web server and audio.cpp.
export const config = {
  ttsBase: defaults.ttsBase,
  asrBase: defaults.asrBase,
  // Kept for reference; the bridges proxy to this.
  audiocppUri: "http://localhost:8080",
};

// Runtime overrides (loaded from localStorage). Enables testing the playground
// against non-local hosts without editing source.
const KEY = "wyoming_audiocpp_demo.ports";
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
