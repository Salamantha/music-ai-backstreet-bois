"use client";

import type { AnalyzeResponse, Profile } from "@/lib/api";

function Bars({ data, alt = false, max = 6 }: {
  data: Record<string, number>; alt?: boolean; max?: number;
}) {
  const rows = Object.entries(data).sort((a, b) => b[1] - a[1]).slice(0, max);
  if (rows.length === 0) return <p className="sub" style={{ margin: 0 }}>—</p>;
  const top = rows[0][1] || 1;
  return (
    <>
      {rows.map(([k, v]) => (
        <div className="bars" key={k}>
          <span>{k}</span>
          <span className={`bar${alt ? " alt" : ""}`}>
            <span style={{ width: `${Math.max(4, (v / top) * 100)}%` }} />
          </span>
          <span className="mono" style={{ color: "var(--muted)", fontSize: 12 }}>
            {v.toFixed(2)}
          </span>
        </div>
      ))}
    </>
  );
}

export function SongMatches({ result }: { result: AnalyzeResponse }) {
  if (result.songs.length === 0) return null;
  return (
    <div className="panel">
      <div className="row spread">
        <h2 style={{ margin: 0 }}>Songs using this progression</h2>
        <span className="pill">
          {result.requests_spent} API request{result.requests_spent === 1 ? "" : "s"}
        </span>
      </div>
      <table style={{ marginTop: 12 }}>
        <thead>
          <tr><th>Artist</th><th>Song</th><th>Section</th><th style={{ width: 64 }}>Score</th></tr>
        </thead>
        <tbody>
          {result.songs.slice(0, 12).map((s) => (
            <tr key={`${s.artist}-${s.song}`}>
              <td>{s.artist}</td>
              <td><a href={s.url} target="_blank" rel="noreferrer">{s.song}</a></td>
              <td style={{ color: "var(--muted)" }}>{s.section}</td>
              <td className="mono">{s.score.toFixed(2)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function TasteProfile({ profile }: { profile: Profile }) {
  const h = profile.harmonic;
  return (
    <div className="grid2">
      <div className="panel">
        <h2>Taste</h2>
        <h3 style={{ fontSize: 13, color: "var(--muted)" }}>Genres</h3>
        <Bars data={profile.genres} />
        <h3 style={{ fontSize: 13, color: "var(--muted)", marginTop: 14 }}>Moods</h3>
        <Bars data={profile.moods} alt max={4} />
        <h3 style={{ fontSize: 13, color: "var(--muted)", marginTop: 14 }}>Eras</h3>
        <Bars data={profile.eras} alt max={3} />
      </div>
      <div className="panel">
        <h2>How you play</h2>
        <p className="sub" style={{ marginTop: -4 }}>
          Measured from your performance alone — no song match needed.
        </p>
        <Bars
          data={{
            "seventh chords": h.seventh_density,
            "borrowed chords": h.borrowed_rate,
            "harmonic variety": h.chord_variety,
            "progression rarity": Math.min(h.mean_progression_rarity / 2, 1),
            "pitch coverage": h.key_spread,
            ...Object.fromEntries(
              Object.entries(h.cadence_profile).map(([k, v]) => [`${k} cadences`, v]),
            ),
          }}
        />
      </div>
    </div>
  );
}

export function MatchList({ result }: { result: AnalyzeResponse }) {
  if (result.matches.length === 0) return null;
  return (
    <div className="panel">
      <h2>Musicians you&apos;d click with</h2>
      {result.matches.map((m) => (
        <div className="match" key={m.id}>
          <div className="row spread">
            <h3 style={{ margin: 0 }}>
              {m.name}{" "}
              <span className="meta">· {m.instrument} · {m.city}</span>
            </h3>
            <span className="pill ok">
              closer than {Math.round(m.percentile * 100)}%
            </span>
          </div>
          <p className="why">{m.rationale}</p>
          <p className="meta" style={{ margin: "6px 0 0" }}>
            {m.bio}
          </p>
        </div>
      ))}
    </div>
  );
}
