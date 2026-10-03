"use client";

import { useEffect, useState, useCallback } from "react";
import { api } from "../lib/api";

export function VoiceSelector({
  ttsBase,
}: {
  ttsBase: string;
}) {
  const [text, setText] = useState("");
  const [voiceName, setVoiceName] = useState("");
  const [voices, setVoices] = useState<{ name: string; model: string }[]>([]);
  const [loading, setLoading] = useState(true);
  const [synthesizing, setSynthesizing] = useState(false);
  const [audioUrl, setAudioUrl] = useState<string | null>(null);
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

  const synthesize = useCallback(async () => {
    if (!text.trim()) return;
    setError("");
    setSynthesizing(true);
    try {
      const res = await api.textToSpeech(text, voiceName || undefined);
      const blob = await res.blob();
      if (audioUrl) URL.revokeObjectURL(audioUrl);
      const url = URL.createObjectURL(blob);
      setAudioUrl(url);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "TTS failed.");
    } finally {
      setSynthesizing(false);
    }
  }, [text, voiceName, audioUrl]);

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
          className="rounded border border-zinc-300 bg-white p-1.5 text-zinc-900 dark:border-zinc-700 dark:bg-zinc-800 dark:text-zinc-100"
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
          className="cursor-pointer rounded bg-blue-600 px-4 py-2 font-medium text-white hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-50"
          onClick={synthesize}
          disabled={synthesizing || loading || !text.trim()}
        >
          {synthesizing ? "Synthesizing…" : "Synthesize"}
        </button>
      </div>
      {audioUrl && <audio src={audioUrl} controls className="w-full" />}
      {error && <p className="text-sm text-red-600">{error}</p>}

    </section>
  );
}

