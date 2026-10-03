"use client";

import { useEffect, useState, useCallback } from "react";
import { api } from "../lib/api";
import type { Overrides } from "../lib/config";

export function VoiceSelector({
  ttsBase,
  overrides,
  onChange,
}: {
  ttsBase: string;
  overrides: Overrides;
  onChange: (o: Overrides) => void;
}) {
  const [text, setText] = useState("");
  const [voiceName, setVoiceName] = useState("");
  const [voices, setVoices] = useState<{ name: string; model: string }[]>([]);
  const [loading, setLoading] = useState(true);
  const [playing, setPlaying] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    api.getVoices()
      .then((v) => {
        setVoices(v);
        if (v.length > 0) setVoiceName(v[0].name);
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  const play = useCallback(async () => {
    if (!text.trim()) {
      setError("Enter some text first.");
      return;
    }
    setError("");
    setPlaying(true);
    try {
      const res = await api.textToSpeech(text, voiceName || undefined);
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const audio = new Audio(url);
      audio.onended = () => URL.revokeObjectURL(url);
      await audio.play();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "TTS failed.");
    } finally {
      setPlaying(false);
    }
  }, [text, voiceName]);

  return (
    <section className="flex flex-col gap-4 rounded-lg border border-zinc-200 bg-white p-4 dark:border-zinc-800 dark:bg-zinc-900">
      <h2 className="text-lg font-semibold">Text-to-speech</h2>

      <textarea
        className="h-28 w-full resize-none rounded border border-zinc-300 p-2 font-mono text-sm dark:border-zinc-700"
        value={text}
        onChange={(e) => setText(e.target.value)}
        placeholder="Type something to synthesize…"
      />

      <label className="flex flex-col gap-1 text-sm">
        <span className="text-zinc-500">Voice</span>
        <select
          className="rounded border border-zinc-300 p-1.5 dark:border-zinc-700"
          value={voiceName}
          onChange={(e) => setVoiceName(e.target.value)}
          disabled={loading || voices.length === 0}
        >
          {voices.map((v) => (
            <option key={v.name} value={v.name}>
              {v.name} ({v.model})
            </option>
          ))}
          {loading && <option>Loading…</option>}
        </select>
      </label>

      <div className="flex flex-wrap items-center gap-3">
        <button
          className="rounded bg-blue-600 px-4 py-2 font-medium text-white hover:bg-blue-700 disabled:opacity-50"
          onClick={play}
          disabled={playing || loading}
        >
          {playing ? "Playing…" : "Play"}
        </button>
      </div>
      {error && <p className="text-sm text-red-600">{error}</p>}

      <OverridesPanel overrides={overrides} onChange={onChange} />
    </section>
  );
}

function OverridesPanel({
  overrides,
  onChange,
}: {
  overrides: Overrides;
  onChange: (o: Overrides) => void;
}) {
  return null;
}
