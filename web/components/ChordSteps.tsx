"use client";

import { useCallback, useLayoutEffect, useRef, useState } from "react";
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
  onPlay: () => void;
  canPlay: boolean;
  playing: boolean;
  busy: boolean;
}

/** Movement below this is a click, not a drag, so the × and arrows still work. */
const DRAG_THRESHOLD_PX = 4;

interface DragState {
  index: number;
  pointerId: number;
  originX: number;
  originY: number;
  dx: number;
  dy: number;
  target: number;
  /** Card centres measured once at drag start, in viewport coordinates. */
  centres: { x: number; y: number }[];
}

export default function ChordSteps({
  steps, pending, live, onRemove, onReorder, onClear, onAnalyse,
  onPlay, canPlay, playing, busy,
}: Props) {
  const [drag, setDrag] = useState<DragState | null>(null);
  const cardRefs = useRef<(HTMLDivElement | null)[]>([]);
  const dragRef = useRef<DragState | null>(null);

  useLayoutEffect(() => { dragRef.current = drag; }, [drag]);

  const begin = useCallback(
    (index: number, e: React.PointerEvent<HTMLDivElement>) => {
      if (busy || steps.length < 2) return;
      // Let the buttons on the card do their own thing.
      if ((e.target as HTMLElement).closest("button")) return;

      const centres = cardRefs.current.slice(0, steps.length).map((el) => {
        const r = el!.getBoundingClientRect();
        return { x: r.left + r.width / 2, y: r.top + r.height / 2 };
      });
      (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId);
      setDrag({
        index, pointerId: e.pointerId,
        originX: e.clientX, originY: e.clientY,
        dx: 0, dy: 0, target: index, centres,
      });
    },
    [busy, steps.length],
  );

  const move = useCallback((e: React.PointerEvent) => {
    const current = dragRef.current;
    if (!current || e.pointerId !== current.pointerId) return;
    const dx = e.clientX - current.originX;
    const dy = e.clientY - current.originY;

    // Land in the slot whose centre is nearest the pointer. Distance in two
    // dimensions so this keeps working when the row wraps.
    let target = current.index;
    let best = Infinity;
    current.centres.forEach((c, i) => {
      const d = (c.x - e.clientX) ** 2 + (c.y - e.clientY) ** 2;
      if (d < best) { best = d; target = i; }
    });

    setDrag({ ...current, dx, dy, target });
  }, []);

  const end = useCallback(
    (e: React.PointerEvent) => {
      const current = dragRef.current;
      if (!current || e.pointerId !== current.pointerId) return;
      const moved =
        Math.abs(current.dx) > DRAG_THRESHOLD_PX ||
        Math.abs(current.dy) > DRAG_THRESHOLD_PX;
      if (moved && current.target !== current.index) {
        onReorder(current.index, current.target);
      }
      setDrag(null);
    },
    [onReorder],
  );

  /** How far a card shifts to open a gap where the dragged one will land. */
  function slotOffset(i: number): string {
    if (!drag || i === drag.index) return "";
    const { index, target } = drag;
    const from = cardRefs.current[index]?.getBoundingClientRect();
    if (!from) return "";
    const step = from.width + 8;  // card width plus the flex gap
    if (index < target && i > index && i <= target) return `translateX(${-step}px)`;
    if (index > target && i >= target && i < index) return `translateX(${step}px)`;
    return "";
  }

  return (
    <div className="panel">
      <div className="row spread">
        <h3 style={{ margin: 0 }}>Chord progression</h3>
        <span className="row" style={{ gap: 8 }}>
          <span className="pill">{steps.length} chord{steps.length === 1 ? "" : "s"}</span>
          {steps.length > 0 && (
            <button
              onClick={onPlay}
              disabled={busy || !canPlay}
              style={{ padding: "5px 11px", fontSize: 13 }}
              title={
                canPlay
                  ? "Send the progression back out to the ChordCat"
                  : "Connect MIDI to play back to the device"
              }
            >
              {playing ? "■ Stop" : "▶ Play"}
            </button>
          )}
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
            Find my matches
          </button>
        </span>
      </div>

      <p className="sub">
        Drag a chord to move it, or use the Move earlier, Move later and Remove
        buttons on each one.
      </p>

      <div className="chords">
        {steps.map((s, i) => {
          const held = drag?.index === i;
          return (
            <div
              className={`chord step${held ? " held" : ""}`}
              key={s.id}
              ref={(el) => { cardRefs.current[i] = el; }}
              onPointerDown={(e) => begin(i, e)}
              onPointerMove={move}
              onPointerUp={end}
              onPointerCancel={end}
              style={{
                transform: held
                  ? `translate(${drag!.dx}px, ${drag!.dy}px) scale(1.06)`
                  : slotOffset(i),
                zIndex: held ? 20 : undefined,
                transition: held ? "none" : "transform 160ms ease",
                cursor: steps.length > 1 ? (held ? "grabbing" : "grab") : "default",
              }}
            >
              <div className="step-move">
                <button
                  onClick={() => onReorder(i, i - 1)}
                  disabled={busy || i === 0}
                  aria-label={`Move ${s.chord?.symbol ?? "chord"} earlier`}
                  title={`Move ${s.chord?.symbol ?? "chord"} earlier`}
                >
                  ‹
                </button>
                <button
                  onClick={() => onReorder(i, i + 1)}
                  disabled={busy || i === steps.length - 1}
                  aria-label={`Move ${s.chord?.symbol ?? "chord"} later`}
                  title={`Move ${s.chord?.symbol ?? "chord"} later`}
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
                aria-label={`Remove ${s.chord?.symbol ?? "chord"}`}
                title={`Remove ${s.chord?.symbol ?? "chord"}`}
              >
                ×
              </button>
            </div>
          );
        })}

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
          Could also be {live.candidates.slice(1, 3).map((c) => c.symbol).join(" or ")}
          {live.bass !== live.root ? ` · bass ${live.bass}` : ""}
        </p>
      )}
    </div>
  );
}
