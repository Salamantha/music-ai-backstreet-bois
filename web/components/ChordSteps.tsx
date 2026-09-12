"use client";

import { noteName } from "@/lib/webmidi";
import type { Identified } from "@/lib/api";

export interface Step {
  id: number;
  pitches: number[];
  chord: Identified | null;
}

interface Props {
  steps: Step[];
  pending: number[];
  live: Identified | null;
  onRemove: (id: number) => void;
  onClear: () => void;
  onAnalyse: () => void;
  busy: boolean;
}

export default function ChordSteps({
  steps, pending, live, onRemove, onClear, onAnalyse, busy,
}: Props) {
  return (
    <div className="panel">
      <div className="row spread">
        <h2 style={{ margin: 0 }}>Progression</h2>
        <span className="row" style={{ gap: 8 }}>
          <span className="pill">{steps.length} chord{steps.length === 1 ? "" : "s"}</span>
          {steps.length > 0 && (
            <button onClick={onClear} disabled={busy} style={{ padding: "5px 11px", fontSize: 13 }}>
              Clear
            </button>
          )}
          <button
            className="primary"
            onClick={onAnalyse}
            disabled={busy || steps.length < 2}
            style={{ padding: "6px 13px", fontSize: 13 }}
          >
            Analyse {steps.length >= 2 ? `${steps.length} chords` : ""}
          </button>
        </span>
      </div>

      <p className="sub" style={{ margin: "8px 0 12px" }}>
        Play one chord at a time. Each chord is captured when you release it, so
        hold it as long as you like and change your mind freely.
      </p>

      <div className="chords">
        {steps.map((s, i) => (
          <div className="chord" key={s.id} style={{ position: "relative" }}>
            <div className="sym">{s.chord?.symbol ?? "?"}</div>
            <div className="rom">{s.chord?.roman ?? `${i + 1}`}</div>
            <div className="cp">{s.pitches.map((p) => noteName(p)).join(" ")}</div>
            <button
              onClick={() => onRemove(s.id)}
              disabled={busy}
              title="remove this chord"
              style={{
                position: "absolute", top: -8, right: -8, padding: "0 6px",
                lineHeight: "18px", fontSize: 12, borderRadius: 999,
              }}
            >
              ×
            </button>
          </div>
        ))}

        {pending.length > 0 && (
          <div className="chord" style={{ borderColor: "var(--accent)", borderStyle: "dashed" }}>
            <div className="sym" style={{ color: "var(--accent)" }}>
              {live?.symbol ?? "…"}
            </div>
            <div className="rom">holding</div>
            <div className="cp">{pending.map((p) => noteName(p)).join(" ")}</div>
          </div>
        )}

        {steps.length === 0 && pending.length === 0 && (
          <span className="pill">play a chord to begin</span>
        )}
      </div>

      {live && pending.length > 0 && live.candidates.length > 1 && (
        <p className="sub" style={{ margin: "12px 0 0" }}>
          Also reads as {live.candidates.slice(1, 3).map((c) => c.symbol).join(" or ")}
          {live.bass !== live.root ? ` · bass ${live.bass}` : ""}
        </p>
      )}
    </div>
  );
}
