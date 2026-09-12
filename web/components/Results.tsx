"use client";

import { useState } from "react";
import {
  matchedPositions, stripModifiers, youtubeSearch,
  type AnalyzeResponse, type Profile, type Song,
} from "@/lib/api";

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

/** A song's own progression, with the part you played picked out. */
function ChordString({
  song, played, playedSymbols,
}: { song: Song; played: string[]; playedSymbols: string[] }) {
  if (song.song_chords.length === 0) {
    return (
      <span className="mono" style={{ color: "var(--muted)", fontSize: 12 }}>
        {song.matched_ngrams.join("  ") || "—"}
      </span>
    );
  }
  const hits = matchedPositions(song.song_chords, song.matched_chords);
  const MAX = 16;

  // Window the display around the first match rather than truncating from the
  // start. A long progression whose match sits late would otherwise be shown
  // entirely in grey, reading as a false positive.
  const first = [...hits].sort((a, b) => a - b)[0] ?? 0;
  let from = 0;
  if (song.song_chords.length > MAX && first + song.matched_chords.length > MAX) {
    from = Math.min(
      Math.max(0, first - 2),
      song.song_chords.length - MAX,
    );
  }
  const shown = song.song_chords.slice(from, from + MAX);

  return (
    <span className="mono" style={{ fontSize: 12 }}>
      {from > 0 && <span style={{ color: "var(--muted)" }}>… </span>}
      {shown.map((chord, i) => {
        const at = from + i;
        return (
          <span
            key={at}
            style={{
              color: hits.has(at) ? "var(--accent)" : "var(--muted)",
              fontWeight: hits.has(at) ? 700 : 400,
              marginRight: 5,
            }}
          >
            {chord}
          </span>
        );
      })}
      {from + MAX < song.song_chords.length && (
        <span style={{ color: "var(--muted)" }}>…</span>
      )}
      {/* The same chords can be written several ways depending on which note is
          called home, and the search tries more than one. Say which reading
          found this song, or its numerals look unrelated to the progression
          shown above -- a `i` appearing where the take reads `vi`. */}
      {differsFromPlayed(song.matched_chords, played) && (
        <div style={{ color: "var(--muted)", fontSize: 11, marginTop: 3 }}>
          your {playedSymbols.join(" ")} read as {song.matched_chords.join(" ")}
        </div>
      )}
    </span>
  );
}

/** True when a song matched a different spelling than the one on display. */
function differsFromPlayed(matched: string[], played: string[]): boolean {
  if (matched.length === 0 || played.length === 0) return false;
  const a = matched.map(stripModifiers).join(" ");
  const b = played.map(stripModifiers).join(" ");
  return a !== b;
}

export function SongMatches({ result }: { result: AnalyzeResponse }) {
  const [expanded, setExpanded] = useState(false);
  if (result.songs.length === 0) return null;
  const INITIAL = 20;
  const shown = expanded ? result.songs : result.songs.slice(0, INITIAL);
  return (
    <div className="panel">
      <div className="row spread">
        <h2 style={{ margin: 0 }}>Songs using this progression</h2>
        <span className="row" style={{ gap: 8 }}>
          <span className="pill">
            best match first
          </span>
          <span className="pill">
            {result.requests_spent} API request{result.requests_spent === 1 ? "" : "s"}
          </span>
        </span>
      </div>
      {result.songs.some((s) =>
        differsFromPlayed(s.matched_chords, result.romans),
      ) && (
        <p className="sub" style={{ margin: "8px 0 0" }}>
          Some rows read your chords in a different key. Relative keys share a
          pitch-class set, so {result.chords.map((c) => c.symbol).join(" ")} is{" "}
          {result.romans.join(" ")} in {result.key?.name} and something else
          elsewhere — the same four chords either way. Hooktheory files songs
          under their own key, so both readings are searched.
        </p>
      )}

      <table style={{ marginTop: 12 }}>
        <thead>
          <tr>
            <th>Artist</th><th>Song · section</th><th>Key</th>
            <th>Their chords · yours in green</th>
            <th style={{ width: 62 }} title="How much of the song is the progression you played. Results are ordered by this.">
              Match ↓
            </th>
          </tr>
        </thead>
        <tbody>
          {shown.map((s) => (
            <tr key={`${s.artist}-${s.song}`}>
              <td>{s.artist}</td>
              <td>
                <a
                  href={youtubeSearch(s.artist, s.song)}
                  target="_blank"
                  rel="noreferrer"
                  title="Find it on YouTube"
                >
                  {s.song}
                </a>
                <a
                  href={s.url}
                  target="_blank"
                  rel="noreferrer"
                  title="Open the Hooktheory analysis"
                  style={{ color: "var(--muted)", fontSize: 11, marginLeft: 6 }}
                >
                  theory ↗
                </a>
                {s.section && (
                  <div style={{ color: "var(--muted)", fontSize: 11, marginTop: 2 }}>
                    {s.section}
                    {s.sections.length > 1 && (
                      <span
                        title={`also matches: ${s.sections
                          .filter((x) => x !== s.section)
                          .join(", ")}`}
                      >
                        {" "}+{s.sections.length - 1} more
                      </span>
                    )}
                  </div>
                )}
              </td>
              <td style={{ color: "var(--muted)", whiteSpace: "nowrap" }}>
                {s.song_key || "—"}
              </td>
              <td>
                <ChordString
                  song={s}
                  played={result.romans}
                  playedSymbols={result.chords.map((c) => c.symbol)}
                />
              </td>
              <td
                className="mono"
                title={`relevance score ${s.score.toFixed(2)}`}
                style={{ color: s.coverage >= 0.99 ? "var(--accent)" : undefined }}
              >
                {s.coverage > 0 ? `${Math.round(s.coverage * 100)}%` : "—"}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {result.songs.length > INITIAL && (
        <button
          onClick={() => setExpanded((v) => !v)}
          style={{ marginTop: 10, padding: "6px 12px", fontSize: 13 }}
        >
          {expanded
            ? "Show fewer"
            : `Show all ${result.songs.length} matches`}
        </button>
      )}
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
