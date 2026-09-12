"use client";

import { useEffect, useState } from "react";
import MidiConnect from "@/components/MidiConnect";
import ChordTimeline from "@/components/ChordTimeline";
import KeyPanel from "@/components/KeyPanel";
import { MatchList, SongMatches, TasteProfile } from "@/components/Results";
import { analyze, health, type AnalyzeResponse } from "@/lib/api";
import { DEMOS, synthesize } from "@/lib/demo";
import type { MidiEvent } from "@/lib/webmidi";

export default function Page() {
  const [result, setResult] = useState<AnalyzeResponse | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [backend, setBackend] = useState<Record<string, unknown> | null>(null);
  const [take, setTake] = useState<{ events: MidiEvent[]; elapsed: number } | null>(null);

  useEffect(() => {
    health().then(setBackend).catch(() => setBackend(null));
  }, []);

  async function run(events: MidiEvent[], elapsed: number, key?: { pc: number; mode: string }) {
    setBusy(true);
    setError("");
    try {
      const res = await analyze(events, {
        sessionEndMs: elapsed,
        keyTonicPc: key?.pc,
        keyMode: key?.mode,
      });
      setResult(res);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  function onEvents(events: MidiEvent[], elapsed: number) {
    setTake({ events, elapsed });
    void run(events, elapsed);
  }

  function override(pc: number, mode: string) {
    if (take) void run(take.events, take.elapsed, { pc, mode });
  }

  return (
    <main>
      <div className="row spread">
        <div>
          <h1>ChordCat Connect</h1>
          <p className="sub">
            Play a progression on your ChordCat. Find the musicians who hear harmony the way you do.
          </p>
        </div>
        <span className={`pill ${backend ? "ok" : "bad"}`}>
          {backend
            ? `backend up · ${backend.personas} musicians`
            : "backend unreachable"}
        </span>
      </div>

      <MidiConnect onEvents={onEvents} busy={busy} />

      <div className="panel">
        <h2>No ChordCat to hand?</h2>
        <p className="sub" style={{ marginTop: -4 }}>
          Run a synthetic take through the same pipeline to check the stack end to end.
        </p>
        <div className="keys">
          {DEMOS.map((d) => (
            <button
              key={d.id}
              onClick={() => {
                const { events, elapsed } = synthesize(d);
                onEvents(events, elapsed);
              }}
              disabled={busy}
              title={d.hint}
            >
              {d.label}
            </button>
          ))}
        </div>
      </div>

      {busy && <div className="panel"><p style={{ margin: 0 }}>Analysing…</p></div>}
      {error && <div className="panel"><p className="error" style={{ margin: 0 }}>{error}</p></div>}

      {result && (
        <>
          {result.notes.length > 0 && (
            <div className="panel">
              <ul className="note-list">
                {result.notes.map((n) => <li key={n}>{n}</li>)}
              </ul>
            </div>
          )}
          <ChordTimeline result={result} />
          {result.key && (
            <KeyPanel keyInfo={result.key} onOverride={override} busy={busy} />
          )}
          <SongMatches result={result} />
          {result.profile && <TasteProfile profile={result.profile} />}
          <MatchList result={result} />
        </>
      )}
    </main>
  );
}
