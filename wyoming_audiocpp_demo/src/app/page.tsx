"use client";

import { useState, useEffect } from "react";
import { VoiceSelector, loadModels } from "../components/VoiceSelector";
import { AsrUpload } from "../components/AsrUpload";
import type { Overrides } from "../lib/config";

export const headers = {};

export default function Home() {
  const [models, setModels] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [overrides, setOverrides] = useState<Overrides>({
    ttsBase: "http://localhost:11201",
    asrBase: "http://localhost:11301",
  });

  useEffect(() => {
    let active = true;
    (async () => {
      try {
        const list = await loadModels(overrides.asrBase);
      } catch {
        // models unavailable (bridges down) — selectors degrade gracefully
      } finally {
        if (active) setLoading(false);
      }
    })();
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    const key = "wyoming_audiocpp_demo.ports";
    try {
      window.localStorage.setItem(key, JSON.stringify(overrides));
    } catch {
      /* ignore */
    }
  }, [overrides]);

  return (
    <div className="flex flex-1 flex-col items-center bg-zinc-50 font-sans dark:bg-black">
      <main className="flex w-full max-w-5xl flex-1 flex-col gap-6 py-8 px-4 sm:px-8">
        <header className="flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <h1 className="text-2xl font-semibold tracking-tight">Wyoming TTS/ASR Playground</h1>
            <p className="text-sm text-zinc-500">
              Wyoming bridges · TTS <code className="rounded bg-black/[.04] px-1 py-0.5 dark:bg-white/[.06]">:11201</code> · ASR{" "}
              <code className="rounded bg-black/[.04] px-1 py-0.5 dark:bg-white/[.06]">:11301</code>
            </p>
          </div>
          <StatusRow models={models} loading={loading} ttsBase={overrides.ttsBase} asrBase={overrides.asrBase} />
        </header>

        {loading && <p className="text-sm text-zinc-500">Loading models…</p>}

        <div className="grid flex-1 gap-6 md:grid-cols-2">
          <VoiceSelector models={models} overrides={overrides} ttsBase={overrides.ttsBase} onChange={setOverrides} />
          <AsrUpload overrides={overrides} onChange={setOverrides} />
        </div>

        <footer className="text-xs text-zinc-400">
          Point the endpoint overrides at your deployed bridges to test outside localhost.
        </footer>
      </main>
    </div>
  );
}

function StatusRow({
  models,
  loading,
  ttsBase,
  asrBase,
}: {
  models: string[];
  loading: boolean;
  ttsBase: string;
  asrBase: string;
}) {
  return (
    <dl className="flex flex-wrap items-center gap-4 text-xs">
      <Stat label="Models" value={loading ? "—" : `${models.length}`} />
      <Stat label="TTS" value={ttsBase} />
      <Stat label="ASR" value={asrBase} />
    </dl>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex flex-col">
      <span className="text-zinc-400">{label}</span>
      <span className="font-medium">{value}</span>
    </div>
  );
}
