"use client";

import type { AnalyzeResponse } from "@/lib/api";

export default function ChordTimeline({ result }: { result: AnalyzeResponse }) {
  const holes = new Map(result.unmapped.map((u) => [u.index, u]));

  return (
    <div className="panel">
      <div className="row spread">
        <h2 style={{ margin: 0 }}>Progression</h2>
        <span className="row" style={{ gap: 8 }}>
          <span className="pill mono">{result.cp || "no cp tokens"}</span>
          {result.alternate_cp && (
            <span className="pill mono" style={{ opacity: 0.65 }}>
              {result.alternate_cp}
            </span>
          )}
        </span>
      </div>

      <div className="chords" style={{ marginTop: 14 }}>
        {result.chords.map((c) => {
          const hole = holes.get(c.index);
          return (
            <div key={c.index} className={`chord${hole ? " hole" : ""}`}>
              <div className="sym">{c.symbol}</div>
              <div className="rom">{c.roman ?? "—"}</div>
              {/* The relative reading. Which of the two is home cannot be
                  decided from the notes, and a player often thinks in the one
                  we did not pick. */}
              {result.alternate_romans[c.index] && (
                <div className="rom alt">{result.alternate_romans[c.index]}</div>
              )}
              <div className="cp">{c.cp ?? (hole ? "no cp" : "")}</div>
            </div>
          );
        })}
      </div>

      {result.alternate_key_name && (
        <p className="sub" style={{ margin: "12px 0 0" }}>
          Top row reads it in {result.key?.name}; below it, the same chords in{" "}
          {result.alternate_key_name}.
        </p>
      )}

      {result.unmapped.length > 0 && (
        <p className="sub" style={{ margin: "12px 0 0" }}>
          {result.unmapped.length} chord(s) have no Hooktheory representation, so the
          progression was searched in segments rather than across them.
        </p>
      )}
    </div>
  );
}
