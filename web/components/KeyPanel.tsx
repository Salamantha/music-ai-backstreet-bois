"use client";

import type { KeyInfo } from "@/lib/api";

interface Props {
  keyInfo: KeyInfo;
  onOverride: (tonicPc: number, mode: string) => void;
  busy: boolean;
}

export default function KeyPanel({ keyInfo, onOverride, busy }: Props) {
  return (
    <div className="panel">
      <div className="row spread">
        <h2 style={{ margin: 0 }}>Key</h2>
        <span className="pill">
          {keyInfo.source === "user" ? "your choice"
            : keyInfo.source === "matched" ? "confirmed by song matches"
            : `${Math.round(keyInfo.confidence * 100)}% confident`}
        </span>
      </div>

      <h3 style={{ marginTop: 10, fontSize: 20 }}>{keyInfo.name}</h3>

      {keyInfo.alternatives.length > 0 && (
        <>
          <p className="sub" style={{ margin: "8px 0 0" }}>
            Several keys use exactly these notes, so this is our best guess.
            Pick a different one if it sounds wrong to you:
          </p>
          <div className="keys">
            {keyInfo.alternatives.slice(0, 4).map((a) => (
              <button
                key={`${a.tonic_pc}-${a.mode}`}
                onClick={() => onOverride(a.tonic_pc, a.mode)}
                disabled={busy}
              >
                {a.name} <span style={{ opacity: 0.6 }}>{Math.round(a.confidence * 100)}%</span>
              </button>
            ))}
          </div>
        </>
      )}

      {keyInfo.modulation_suspected && (
        <p className="sub" style={{ margin: "10px 0 0" }}>
          Your chords seem to change key partway through, so we searched each
          part on its own.
        </p>
      )}
    </div>
  );
}
