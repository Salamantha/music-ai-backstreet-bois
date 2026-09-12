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
            Relative keys share a pitch-class set, so this is genuinely ambiguous
            from the notes alone. Override it if it looks wrong:
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
          A key change was detected. Search windows do not span it.
        </p>
      )}
    </div>
  );
}
