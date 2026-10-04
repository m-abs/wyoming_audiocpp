"use client";

import { useEffect, useRef, useState, useCallback } from "react";
import { api } from "../lib/api";

type TtsEntry = {
  id: string;
  text: string;
  voice: string;
  timestamp: string; // ISO string; formatted for the label + filename.
  url: string; // in-memory object URL (not persisted across page loads)
  durationMs: number; // how long synthesis took, shown below the audio element
};

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
  const [history, setHistory] = useState<TtsEntry[]>([]);
  const [error, setError] = useState("");
  // Object URLs created this session; released on unmount. History is in-memory only.
  const urlsRef = useRef<string[]>([]);

  useEffect(() => {
    api.getVoices()
      .then((v) => {
        setVoices(v);
        if (v.length > 0) setVoiceName(v[0].name);
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  // Release every object URL when the component unmounts. The ref is stable, so
  // this cleanup runs once and never revokes URLs of entries that survive re-renders.
  useEffect(() => {
    const urls = urlsRef.current;
    return () => {
      urls.forEach((u) => URL.revokeObjectURL(u));
    };
  }, []);

  const synthesize = useCallback(async () => {
    if (!text.trim()) return;
    setError("");
    setSynthesizing(true);
    const start = performance.now();
    try {
      const res = await api.textToSpeech(text, voiceName || undefined);
      const blob = await res.blob();
      const durationMs = performance.now() - start;
      const url = URL.createObjectURL(blob);
      urlsRef.current.push(url);
      const entry: TtsEntry = {
        id: crypto.randomUUID(),
        text,
        voice: voiceName,
        timestamp: new Date().toISOString(),
        url,
        durationMs,
      };
      setHistory((prev) => [entry, ...prev]);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "TTS failed.");
    } finally {
      setSynthesizing(false);
    }
  }, [text, voiceName]);

  const save = useCallback((entry: TtsEntry) => {
    const a = document.createElement("a");
    a.href = entry.url;
    a.download = `tts_${entry.voice.replace(/[^a-zA-Z0-9_]/g, "_")}_${entry.timestamp.replace(/[:T]/g, "-")}.wav`;
    a.click();
  }, []);

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

      {history.length > 0 && (
        <div className="flex flex-col gap-3">
          {history.map((entry) => (
            <div key={entry.id} className="rounded border border-zinc-200 p-3 dark:border-zinc-800">
              <div className="mb-2 flex items-center justify-between text-sm">
                <span className="text-zinc-500">{entry.voice}</span>
                <span className="text-xs text-zinc-400">
                  {new Date(entry.timestamp).toLocaleString()}
                </span>
              </div>
              <div className="flex items-center gap-2">
                <audio src={entry.url} controls className="min-w-0 flex-1" />
                <button
                  className="cursor-pointer whitespace-nowrap rounded border border-zinc-300 px-3 py-1.5 text-sm hover:bg-zinc-100 dark:border-zinc-700 dark:hover:bg-zinc-800"
                  onClick={() => save(entry)}
                >
                  Save
                </button>
              </div>
              <div className="mt-2 text-xs text-zinc-400">
                Processed in {entry.durationMs >= 1000 ? `${(entry.durationMs / 1000).toFixed(2)}s` : `${Math.round(entry.durationMs)}ms`}
              </div>
            </div>
          ))}
        </div>
      )}

      {error && <p className="text-sm text-red-600">{error}</p>}
    </section>
  );
}
