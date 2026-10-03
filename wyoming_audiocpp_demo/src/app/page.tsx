"use client";

import { useState } from "react";
import { VoiceSelector } from "../components/VoiceSelector";
import { AsrUpload } from "../components/AsrUpload";
import type { Overrides } from "../lib/config";

export const headers = {};

export default function Home() {
  const [overrides, setOverrides] = useState<Overrides>({
    ttsBase: "http://localhost:5001",
    asrBase: "http://localhost:5000",
  });

  return (
    <div className="flex flex-1 flex-col items-center bg-zinc-50 font-sans dark:bg-black">
      <main className="flex w-full max-w-5xl flex-1 flex-col gap-6 py-8 px-4 sm:px-8">
        <header className="flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <h1 className="text-2xl font-semibold tracking-tight">Wyoming Audio.cpp Demo</h1>
            <p className="text-sm text-zinc-500">
              Wyoming bridges · TTS <code className="rounded bg-black/[.04] px-1 py-0.5 dark:bg-white/[.06]">:5001</code> · ASR{" "}
              <code className="rounded bg-black/[.04] px-1 py-0.5 dark:bg-white/[.06]">:5000</code>
            </p>
          </div>
        </header>

        <div className="grid flex-1 gap-6 md:grid-cols-2">
          <VoiceSelector overrides={overrides} ttsBase={overrides.ttsBase} onChange={setOverrides} />
          <AsrUpload overrides={overrides} onChange={setOverrides} />
        </div>

        <footer className="text-xs text-zinc-400">
          Point the endpoint overrides at your deployed bridges to test outside localhost.
        </footer>
      </main>
    </div>
  );
}
