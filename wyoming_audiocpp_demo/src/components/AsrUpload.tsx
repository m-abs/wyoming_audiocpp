"use client";

import { useState, useCallback, useRef, useEffect } from "react";
import { api } from "../lib/api";
import { type Overrides } from "../lib/config";

type AsrEntry = {
  id: string;
  audioUrl: string; // in-memory object URL of the source audio (not persisted)
  text: string;
  timestamp: string; // ISO string
  durationMs: number; // how long transcription took
};

const RATE = 16000;

const fmtMs = (ms: number) =>
  ms >= 1000 ? `${(ms / 1000).toFixed(2)}s` : `${Math.round(ms)}ms`;

// Encode a Float32 PCM mono buffer as a 16-bit / 16 kHz WAV blob.
function encodeWav(samples: Float32Array, sampleRate: number): Blob {
  const numSamples = samples.length;
  const buffer = new ArrayBuffer(44 + numSamples * 2);
  const view = new DataView(buffer);
  const writeStr = (offset: number, s: string) => {
    for (let i = 0; i < s.length; i++) view.setUint8(offset + i, s.charCodeAt(i));
  };
  writeStr(0, "RIFF");
  view.setUint32(4, 36 + numSamples * 2, true);
  writeStr(8, "WAVE");
  writeStr(12, "fmt ");
  view.setUint32(16, 16, true); // fmt chunk size
  view.setUint16(20, 1, true); // PCM
  view.setUint16(22, 1, true); // mono
  view.setUint32(24, sampleRate, true);
  view.setUint32(28, sampleRate * 2, true); // byte rate
  view.setUint16(32, 2, true); // block align
  view.setUint16(34, 16, true); // bits per sample
  writeStr(36, "data");
  view.setUint32(40, numSamples * 2, true);
  for (let i = 0; i < numSamples; i++) {
    const s = Math.max(-1, Math.min(1, samples[i]));
    view.setInt16(44 + i * 2, s < 0 ? s * 32768 : s * 32767, true);
  }
  return new Blob([buffer], { type: "audio/wav" });
}

// Convert an arbitrary audio blob (e.g. a recorded webm clip) into a 16-bit /
// 16 kHz mono WAV that audio.cpp can decode. Resampling is done by an
// OfflineAudioContext, which handles the rate change for us.
async function toWavBlob(blob: Blob): Promise<Blob> {
  const decodeCtx = new AudioContext();
  try {
    const decoded = await decodeCtx.decodeAudioData(await blob.arrayBuffer());
    const off = new OfflineAudioContext(1, Math.ceil(decoded.duration * RATE), RATE);
    const src = off.createBufferSource();
    src.buffer = decoded;
    src.connect(off.destination);
    src.start(0);
    const rendered = await off.startRendering();
    return encodeWav(rendered.getChannelData(0), RATE);
  } finally {
    void decodeCtx.close();
  }
}

export function AsrUpload({ overrides }: { overrides: Overrides }) {
  const [source, setSource] = useState<"file" | "mic">("file");
  const [file, setFile] = useState<File | null>(null);
  const [micWav, setMicWav] = useState<Blob | null>(null);
  const [recording, setRecording] = useState(false);
  const [languages, setLanguages] = useState<string[]>([]);
  const [languageLoading, setLanguageLoading] = useState(true);
  const [language, setLanguage] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [history, setHistory] = useState<AsrEntry[]>([]);
  const inputRef = useRef<HTMLInputElement>(null);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  // Object URLs created this session; released on unmount. History is in-memory only.
  const urlsRef = useRef<string[]>([]);

  // Release every object URL and stop any live capture when the component unmounts.
  useEffect(() => {
    const urls = urlsRef.current;
    return () => {
      urls.forEach((u) => URL.revokeObjectURL(u));
      streamRef.current?.getTracks().forEach((t) => t.stop());
      if (recorderRef.current && recorderRef.current.state === "recording") {
        recorderRef.current.stop();
      }
    };
  }, []);

  // Fetch the configured languages for the single ASR model. The language field is
  // read-only when zero or one language is configured; a select box when multiple.
  useEffect(() => {
    api.getAsrLanguages()
      .then((langs) => {
        setLanguages(langs);
        setLanguage(langs.length === 0 ? "auto" : langs[0]);
      })
      .catch(() => {
        setLanguages([]);
        setLanguage("auto");
      })
      .finally(() => setLanguageLoading(false));
  }, []);

  const handleFile = useCallback((f: File) => {
    if (f.type && !f.type.startsWith("audio/")) {
      setError("Only audio files are accepted (WAV expected).");
      return;
    }
    setFile(f);
    setError("");
  }, []);

  const startRecording = useCallback(async () => {
    setError("");
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      chunksRef.current = [];
      const recorder = new MediaRecorder(stream);
      recorder.ondataavailable = (e) => e.data.size > 0 && chunksRef.current.push(e.data);
      recorder.start();
      recorderRef.current = recorder;
      streamRef.current = stream;
      setRecording(true);
    } catch (e: unknown) {
      setError(
        e instanceof Error ? `Microphone unavailable: ${e.message}` : "Microphone unavailable.",
      );
    }
  }, []);

  const stopRecording = useCallback(async () => {
    const recorder = recorderRef.current;
    if (!recorder || !recording) return;
    setRecording(false);
    await new Promise<void>((resolve) => {
      recorder.onstop = () => resolve();
      recorder.stop(); // must fire inside the executor: stop() triggers onstop, which resolves the awaited promise
    });
    streamRef.current?.getTracks().forEach((t) => t.stop());
    streamRef.current = null;
    const blob = new Blob(chunksRef.current, { type: "audio/webm" });
    try {
      setMicWav(await toWavBlob(blob));
    } catch (e: unknown) {
      setError(
        e instanceof Error ? `Could not process recording: ${e.message}` : "Could not process recording.",
      );
    }
  }, [recording]);

  const submit = useCallback(async () => {
    const blob = source === "file" ? file : micWav;
    if (!blob) {
      setError(source === "file" ? "Choose a WAV file first." : "Record some speech first.");
      return;
    }
    setLoading(true);
    setError("");
    const start = performance.now();
    try {
      const f = new File([blob], "audio.wav", { type: "audio/wav" });
      const data = await api.speechToText(f, language || undefined);
      const durationMs = performance.now() - start;
      const url = URL.createObjectURL(blob);
      urlsRef.current.push(url);
      setHistory((prev) => [
        {
          id: crypto.randomUUID(),
          audioUrl: url,
          text: data.text ?? "",
          timestamp: new Date().toISOString(),
          durationMs,
        },
        ...prev,
      ]);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "ASR failed.");
    } finally {
      setLoading(false);
    }
  }, [source, file, micWav, language]);

  const seg = (active: boolean) =>
    `cursor-pointer rounded px-3 py-1.5 text-sm ${
      active ? "bg-white text-zinc-900 shadow dark:bg-zinc-700 dark:text-zinc-100" : "text-zinc-600 hover:text-zinc-900 dark:text-zinc-400 dark:hover:text-zinc-100"
    }`;

  const hasSource = source === "file" ? !!file : !!micWav;

  return (
    <section className="flex flex-col gap-4 rounded-lg border border-zinc-200 bg-white p-4 dark:border-zinc-800 dark:bg-zinc-900">
      <h2 className="text-lg font-semibold">Speech-to-text</h2>

      <div className="flex gap-1 rounded-md bg-zinc-100 p-1 dark:bg-zinc-800">
        <button className={seg(source === "file")} onClick={() => setSource("file")}>
          Pick a file
        </button>
        <button className={seg(source === "mic")} onClick={() => setSource("mic")}>
          Microphone
        </button>
      </div>

      {source === "file" ? (
        <>
          <input
            ref={inputRef}
            type="file"
            accept=".wav,.WAV,audio/wav"
            onChange={(e) => e.target.files?.[0] && handleFile(e.target.files[0])}
            className="file:mr-4 file:rounded-full file:border-0 file:bg-violet-50 file:px-4 file:py-2 file:text-sm file:font-semibold hover:file:bg-blue-100 dark:file:bg-blue-600 dark:file:text-blue-100 dark:hover:file:bg-blue-500"
          />
          <p className="text-xs text-zinc-500">
            16-bit 16 kHz mono WAV recommended. Other formats are rejected by audio.cpp at decode.
          </p>
        </>
      ) : (
        <div className="flex flex-col gap-2">
          {recording ? (
            <>
              <span className="flex items-center gap-2 text-sm text-red-600">
                <span className="h-3 w-3 animate-pulse rounded-full bg-red-600" /> Recording…
              </span>
              <button
                className="cursor-pointer rounded bg-red-600 px-4 py-2 font-medium text-white hover:bg-red-700"
                onClick={stopRecording}
              >
                Stop
              </button>
            </>
          ) : (
            <>
              <button
                className="cursor-pointer rounded bg-blue-600 px-4 py-2 font-medium text-white hover:bg-blue-700"
                onClick={startRecording}
              >
                Start recording
              </button>
              {micWav && (
                <p className="text-xs text-zinc-500">
                  Recorded clip ready ({(micWav.size / 1024).toFixed(1)} KB WAV, 16 kHz mono).
                </p>
              )}
            </>
          )}
        </div>
      )}

      <label className="flex flex-col gap-1 text-sm">
        <span className="text-zinc-500">Language</span>
        {languageLoading ? (
          <div className="rounded border border-zinc-300 p-1.5 text-zinc-500 dark:border-zinc-700">
            Loading…
          </div>
        ) : languages.length > 1 ? (
          <select
            className="rounded border border-zinc-300 bg-white p-1.5 text-zinc-900 dark:border-zinc-700 dark:bg-zinc-800 dark:text-zinc-100"
            value={language}
            onChange={(e) => setLanguage(e.target.value)}
          >
            {languages.map((lang) => (
              <option key={lang} value={lang}>
                {lang}
              </option>
            ))}
          </select>
        ) : (
          <input
            className="rounded border border-zinc-300 bg-zinc-50 p-1.5 dark:border-zinc-700 dark:bg-zinc-800"
            value={language}
            readOnly
          />
        )}
      </label>

      <div className="flex flex-wrap items-center gap-3">
        <button
          className="cursor-pointer rounded bg-blue-600 px-4 py-2 font-medium text-white hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-50"
          onClick={submit}
          disabled={loading || recording || !hasSource}
        >
          {loading ? "Transcribing…" : "Transcribe"}
        </button>
      </div>

      {error && <p className="text-sm text-red-600">{error}</p>}

      {history.length > 0 && (
        <div className="flex flex-col gap-3">
          <h3 className="text-sm font-semibold text-zinc-500">History</h3>
          {history.map((entry) => (
            <div key={entry.id} className="rounded border border-zinc-200 p-3 dark:border-zinc-800">
              <div className="mb-2 flex items-center justify-between text-xs text-zinc-400">
                <span>{new Date(entry.timestamp).toLocaleString()}</span>
                <span>Processed in {fmtMs(entry.durationMs)}</span>
              </div>
              <audio src={entry.audioUrl} controls className="min-w-0" />
              <p className="mt-2 whitespace-pre-wrap break-words text-sm">
                {entry.text || "(empty)"}
              </p>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}
