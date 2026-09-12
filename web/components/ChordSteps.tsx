"use client";

import { useState } from "react";
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
  onReorder: (from: number, to: number) => void;
  onClear: () => void;
  onAnalyse: () => void;
  busy: boolean;
}

export default function ChordSteps({
  steps, pending, live, onRemove, onReorder, onClear, onAnalyse, busy,
}: Props) {
  // Index of the card being dragged, and the slot it would land in.
  const [dragging, setDragging] = useState<number | null>(null);
  const [over, setOver] = useState<number | null>(null);

  function drop(to: number) {
    if (dragging !== null && dragging !== to) onReorder(dragging, to);
    setDragging(null);
    setOver(null);
  }

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
            disabled={busy || steps.length < 1}
            style={{ padding: "6px 13px", fontSize: 13 }}
          >
            Analyse {steps.length === 1 ? "1 chord" : steps.length > 1 ? `${steps.length} chords` : ""}
          </button>
        </span>
      </div>

      <p className="sub" style={{ margin: "8px 0 12px" }}>
        Play one chord at a time — each is captured when you release it. Drag a
        chord, or use its arrows, to change the order.
      </p>

      <div className="chords">
        {steps.map((s, i) => (
          <div
            className={`chord${over === i && dragging !== i ? " drop-target" : ""}`}
            key={s.id}
            style={{ position: "relative", opacity: dragging === i ? 0.4 : 1 }}
            draggable={!busy}
            onDragStart={() => setDragging(i)}
            onDragEnd={() => { setDragging(null); setOver(null); }}
            onDragOver={(e) => { e.preventDefault(); setOver(i); }}
            onDrop={(e) => { e.preventDefault(); drop(i); }}
          >
            <div className="step-move">
              <button
                onClick={() => onReorder(i, i - 1)}
                disabled={busy || i === 0}
                aria-label={`move ${s.chord?.symbol ?? "chord"} earlier`}
                title="move earlier"
              >
                ‹
              </button>
              <button
                onClick={() => onReorder(i, i + 1)}
                disabled={busy || i === steps.length - 1}
                aria-label={`move ${s.chord?.symbol ?? "chord"} later`}
                title="move later"
              >
                ›
              </button>
            </div>
            <div className="sym">{s.chord?.symbol ?? "?"}</div>
            <div className="rom">{s.chord?.roman ?? `${i + 1}`}</div>
            <div className="cp">{s.pitches.map((p) => noteName(p)).join(" ")}</div>
            <button
              className="step-remove"
              onClick={() => onRemove(s.id)}
              disabled={busy}
              aria-label={`remove ${s.chord?.symbol ?? "chord"}`}
              title="remove this chord"
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
