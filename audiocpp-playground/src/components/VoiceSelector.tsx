"use client";

import { useMemo, useState, useCallback } from "react";
import type { VoiceConfig } from "../lib/api";
import type { Overrides } from "../lib/config";

export async function loadModels(): Promise<string[]> {
  const info = await (await fetch("/api/info")).json();
  const asr = (info?.asr ?? []).map((m: { name?: string }) => m.name);
  // Ensure the TTS default (omnivoice) is offered even if ASR filters it out.
  if (!asr.includes("omnivoice")) asr.push("omnivoice");
  return asr;
}

export function VoiceSelector({
  models,
  overrides,
  ttsBase,
  onChange,
}: {
  models: string[];
  overrides: Overrides;
  ttsBase: string;
  onChange: (o: Overrides) => void;
}) {
  const [text, setText] = useState("");
  const [model, setModel] = useState("omnivoice");
  const [voice, setVoice] = useState("");
  const [language, setLanguage] = useState("");
  const [speed, setSpeed] = useState("");
  const [instruct, setInstruct] = useState("");
  const [playing, setPlaying] = useState(false);
  const [error, setError] = useState("");

  const [modelSet, voiceSet, languageSet, speedSet, instructSet] = useMemo(
    () => [Boolean(model), Boolean(voice), Boolean(language), Boolean(speed), Boolean(instruct)],
    [model, voice, language, speed, instruct],
  );

  const voiceConfig: VoiceConfig | undefined =
    modelSet || voiceSet || languageSet || speedSet || instructSet
      ? {
          ...(modelSet ? { model } : {}),
          ...(voiceSet ? { name: voice } : {}),
          ...(languageSet ? { language } : {}),
          ...(speedSet ? { speed: Number(speed) } : {}),
          ...(instructSet ? { instruct } : {}),
        }
      : undefined;

  const play = useCallback(async () => {
    if (!text.trim()) {
      setError("Enter some text first.");
      return;
    }
    setError("");
    setPlaying(true);
    try {
      const res = await fetch(`${ttsBase}/api/tts`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text, voice: voiceConfig }),
      });
      if (!res.ok) throw new Error(await res.text());
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
  }, [text, voiceConfig, ttsBase]);

  return (
    <section className="flex flex-col gap-4 rounded-lg border border-zinc-200 bg-white p-4 dark:border-zinc-800 dark:bg-zinc-900">
      <h2 className="text-lg font-semibold">Text-to-speech</h2>

      <textarea
        className="h-28 w-full resize-none rounded border border-zinc-300 p-2 font-mono text-sm dark:border-zinc-700"
        value={text}
        onChange={(e) => setText(e.target.value)}
        placeholder="Type something to synthesize…"
      />

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
        <label className="flex flex-col gap-1 text-sm">
          <span className="text-zinc-500">Model</span>
          <select
            className="rounded border border-zinc-300 p-1.5 dark:border-zinc-700"
            value={model}
            onChange={(e) => setModel(e.target.value)}
          >
            {models.map((m) => (
              <option key={m} value={m}>
                {m}
              </option>
            ))}
          </select>
        </label>
        <label className="flex flex-col gap-1 text-sm">
          <span className="text-zinc-500">Voice</span>
          <input
            className="rounded border border-zinc-300 p-1.5 dark:border-zinc-700"
            value={voice}
            onChange={(e) => setVoice(e.target.value)}
            placeholder="optional"
          />
        </label>
        <label className="flex flex-col gap-1 text-sm">
          <span className="text-zinc-500">Language</span>
          <input
            className="rounded border border-zinc-300 p-1.5 dark:border-zinc-700"
            value={language}
            onChange={(e) => setLanguage(e.target.value)}
            placeholder="optional"
          />
        </label>
        <label className="flex flex-col gap-1 text-sm">
          <span className="text-zinc-500">Speed</span>
          <input
            className="rounded border border-zinc-300 p-1.5 dark:border-zinc-700"
            value={speed}
            onChange={(e) => setSpeed(e.target.value)}
            placeholder="optional"
          />
        </label>
        <label className="flex flex-col gap-1 text-sm sm:col-span-2">
          <span className="text-zinc-500">Instruct</span>
          <input
            className="w-full rounded border border-zinc-300 p-1.5 dark:border-zinc-700"
            value={instruct}
            onChange={(e) => setInstruct(e.target.value)}
            placeholder="optional"
          />
        </label>
      </div>

      <div className="flex flex-wrap items-center gap-3">
        <button
          className="rounded bg-blue-600 px-4 py-2 font-medium text-white hover:bg-blue-700 disabled:opacity-50"
          onClick={play}
          disabled={playing}
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
  return (
    <fieldset className="flex flex-col gap-2 rounded border border-dashed border-zinc-300 p-3 text-sm dark:border-zinc-700">
      <legend className="text-xs text-zinc-500">Endpoint overrides</legend>
      <label className="flex flex-col gap-0.5">
        <span className="text-zinc-500">TTS base</span>
        <input
          className="rounded border border-zinc-300 p-1 dark:border-zinc-700"
          value={overrides.ttsBase}
          onChange={(e) => onChange({ ...overrides, ttsBase: e.target.value })}
        />
      </label>
      <label className="flex flex-col gap-0.5">
        <span className="text-zinc-500">ASR base</span>
        <input
          className="rounded border border-zinc-300 p-1 dark:border-zinc-700"
          value={overrides.asrBase}
          onChange={(e) => onChange({ ...overrides, asrBase: e.target.value })}
        />
      </label>
      <button
        className="self-start rounded border border-zinc-300 px-2 py-1 text-xs hover:bg-zinc-100 dark:border-zinc-700 dark:hover:bg-zinc-800"
        onClick={() => onChange({ ttsBase: "http://localhost:5001", asrBase: "http://localhost:5002" })}
      >
        Reset
      </button>
    </fieldset>
  );
}
