"use client";

import type { AnalyzeResponse } from "@/lib/api";

export default function ChordTimeline({ result }: { result: AnalyzeResponse }) {
  const holes = new Map(result.unmapped.map((u) => [u.index, u]));

  return (
    <div className="panel">
      <div className="row spread">
        <h2 style={{ margin: 0 }}>Progression</h2>
        <span className="pill mono">{result.cp || "no cp tokens"}</span>
      </div>

      <div className="chords" style={{ marginTop: 14 }}>
        {result.chords.map((c) => {
          const hole = holes.get(c.index);
          return (
            <div key={c.index} className={`chord${hole ? " hole" : ""}`}>
              <div className="sym">{c.symbol}</div>
              <div className="rom">{c.roman ?? "—"}</div>
              <div className="cp">{c.cp ?? (hole ? "no cp" : "")}</div>
            </div>
          );
        })}
      </div>

      {result.unmapped.length > 0 && (
        <p className="sub" style={{ margin: "12px 0 0" }}>
          {result.unmapped.length} chord(s) have no Hooktheory representation, so the
          progression was searched in segments rather than across them.
        </p>
      )}
    </div>
  );
}
