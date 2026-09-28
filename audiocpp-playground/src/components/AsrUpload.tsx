"use client";

import { useState, useCallback, useRef } from "react";
import type { Overrides } from "../lib/config";

export function AsrUpload({
  overrides,
  onChange,
}: {
  overrides: Overrides;
  onChange: (o: Overrides) => void;
}) {
  const [file, setFile] = useState<File | null>(null);
  const [model, setModel] = useState("hviske");
  const [language, setLanguage] = useState("");
  const [transcript, setTranscript] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);

  const handleFile = useCallback((f: File) => {
    if (f.type && !f.type.startsWith("audio/")) {
      setError("Only audio files are accepted (WAV expected).");
      return;
    }
    setFile(f);
    setTranscript("");
    setError("");
  }, []);

  const submit = useCallback(async () => {
    if (!file) {
      setError("Choose a WAV file first.");
      return;
    }
    setLoading(true);
    setError("");
    setTranscript("");
    try {
      const q = new URLSearchParams();
      if (language) q.set("language", language);
      if (model) q.set("model", model);
      const formData = new FormData();
      formData.append("file", file, "audio.wav");
      const res = await fetch(`${overrides.asrBase}/api/speech-to-text?${q.toString()}`, {
        method: "POST",
        body: formData,
      });
      if (!res.ok) throw new Error(await res.text());
      const data = await res.json();
      setTranscript(data.text ?? "");
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "ASR failed.");
    } finally {
      setLoading(false);
    }
  }, [file, language, model, overrides.asrBase]);

  return (
    <section className="flex flex-col gap-4 rounded-lg border border-zinc-200 bg-white p-4 dark:border-zinc-800 dark:bg-zinc-900">
      <h2 className="text-lg font-semibold">Speech-to-text</h2>

      <input
        ref={inputRef}
        type="file"
        accept=".wav,.WAV,audio/wav"
        onChange={(e) => e.target.files?.[0] && handleFile(e.target.files[0])}
        className="text-sm"
      />
      <p className="text-xs text-zinc-500">
        16-bit 16 kHz mono WAV recommended. Other formats are rejected by audio.cpp at decode.
      </p>

      <div className="grid grid-cols-2 gap-3">
        <label className="flex flex-col gap-1 text-sm">
          <span className="text-zinc-500">Model</span>
          <input
            className="rounded border border-zinc-300 p-1.5 dark:border-zinc-700"
            value={model}
            onChange={(e) => setModel(e.target.value)}
          />
        </label>
        <label className="flex flex-col gap-1 text-sm">
          <span className="text-zinc-500">Language</span>
          <input
            className="rounded border border-zinc-300 p-1.5 dark:border-zinc-700"
            value={language}
            onChange={(e) => setLanguage(e.target.value)}
            placeholder="empty = auto-detect"
          />
        </label>
      </div>

      <div className="flex flex-wrap items-center gap-3">
        <button
          className="rounded bg-blue-600 px-4 py-2 font-medium text-white hover:bg-blue-700 disabled:opacity-50"
          onClick={submit}
          disabled={loading || !file}
        >
          {loading ? "Transcribing…" : "Transcribe"}
        </button>
      </div>
      {error && <p className="text-sm text-red-600">{error}</p>}

      {transcript && (
        <div className="flex flex-col gap-2">
          <textarea
            className="h-32 w-full resize-none rounded border border-zinc-300 p-2 font-mono text-sm dark:border-zinc-700"
            value={transcript}
            readOnly
          />
          <button
            className="rounded border border-zinc-300 px-3 py-1.5 text-sm hover:bg-zinc-100 dark:border-zinc-700 dark:hover:bg-zinc-800"
            onClick={() => {
              const blob = new Blob([transcript], { type: "text/plain" });
              const url = URL.createObjectURL(blob);
              const a = document.createElement("a");
              a.href = url;
              a.download = "transcript.txt";
              a.click();
              URL.revokeObjectURL(url);
            }}
          >
            Download text
          </button>
        </div>
      )}

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
