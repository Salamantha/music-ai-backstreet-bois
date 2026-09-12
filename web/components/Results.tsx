"use client";

import { useState } from "react";
import {
  matchedPositions, stripModifiers, youtubeSearch,
  type AnalyzeResponse, type Match, type Profile, type Song,
} from "@/lib/api";
import { BAND, CatFace, type Cat } from "./CatBand";

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
              color: hits.has(at) ? "var(--accent-3)" : "var(--muted)",
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

export function SongMatches({ result, filter }: {
  result: AnalyzeResponse;
  /** The genre filter, which lives with the songs it filters. */
  filter?: React.ReactNode;
}) {
  const [expanded, setExpanded] = useState(false);
  // With a filter attached the panel must survive an empty result: otherwise
  // choosing a genre that matches nothing takes away the control that undoes it.
  if (result.songs.length === 0 && !filter) return null;
  const INITIAL = 20;
  const shown = expanded ? result.songs : result.songs.slice(0, INITIAL);
  return (
    <div className="panel">
      <h2 style={{ margin: 0 }}>Songs using this progression</h2>
      {result.songs.some((s) =>
        differsFromPlayed(s.matched_chords, result.romans),
      ) && (
        <p className="sub" style={{ margin: "8px 0 0" }}>
          Some songs below are in a different key from yours. They still move
          through the same pattern of chords — they just start from a different
          note. Songs are filed under their own key, so we search both ways.
        </p>
      )}

      {filter && <div className="setup">{filter}</div>}

      {result.songs.length === 0 ? (
        <p className="sub" style={{ margin: 0 }}>
          No songs left with that genre chosen. Pick another, or clear it above.
        </p>
      ) : (
      <table style={{ marginTop: 12 }}>
        <thead>
          <tr>
            <th>Artist</th><th>Song · section</th><th>Key</th>
            <th>Their chords · yours highlighted</th>
            <th style={{ width: 62 }} title="How much of the song is the progression you played. Closest first.">
              Match ↓
            </th>
          </tr>
        </thead>
        <tbody>
          {shown.map((s) => (
            <tr key={`${s.artist}-${s.song}`}>
              <td>{s.artist}</td>
              <td>
                {/* Straight to the recording when the source knew which one
                    it is; a search only when it did not. Either way the title
                    is the link -- one destination, no second guess to make. */}
                <a
                  href={s.video_url || youtubeSearch(s.artist, s.song)}
                  target="_blank"
                  rel="noreferrer"
                  aria-label={`${s.song} on YouTube`}
                  title={
                    s.video_url
                      ? "Watch on YouTube"
                      : "Search YouTube for this song"
                  }
                >
                  {s.song}
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
                style={{ color: s.coverage >= 0.99 ? "var(--accent)" : undefined }}
              >
                {s.coverage > 0 ? `${Math.round(s.coverage * 100)}%` : "—"}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      )}
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
  return (
    <div className="panel">
      <h2>Taste</h2>
      <h3 style={{ fontSize: 13, color: "var(--muted)" }}>Genres</h3>
      <Bars data={profile.genres} />
      <h3 style={{ fontSize: 13, color: "var(--muted)", marginTop: 14 }}>Moods</h3>
      <Bars data={profile.moods} alt max={4} />
      <h3 style={{ fontSize: 13, color: "var(--muted)", marginTop: 14 }}>Eras</h3>
      <Bars data={profile.eras} alt max={3} />
    </div>
  );
}

function catFor(name: string): Cat {
  let h = 0;
  for (const ch of name) h = (h * 31 + ch.charCodeAt(0)) >>> 0;
  return BAND[h % BAND.length];
}

const COMPONENT_LABELS: Record<string, string> = {
  genre: "genres", artist: "artists", harmonic: "harmony", mood: "mood", era: "era",
};

export function MatchList({
  matches, roomSize,
}: {
  matches: Match[];
  roomSize?: number;
}) {
  const others = roomSize !== undefined ? roomSize - 1 : undefined;
  return (
    <div className="panel">
      <h2>Musicians you&apos;d click with</h2>
      {matches.length === 0 ? (
        <p className="sub" style={{ marginBottom: 0 }}>
          You&apos;re the first one in the room. Leave this tab open — the next
          person who plays something shows up here.
        </p>
      ) : (
        <>
          <p className="sub">
            {others !== undefined
              ? `${others} other musician${others === 1 ? " has" : "s have"} played their own progression into ChordCat Connect. `
              : "Everyone here has played their own progression into ChordCat Connect. "}
            We compared what you played to what they played — the chords you
            reach for, the keys you sit in, the songs you both turn out to share
            — and these are the closest. Find them and play something.
          </p>
          {matches.map((m, i) => {
            const cat = catFor(m.name);
            const where = [m.instrument, m.city].filter(Boolean).join(" · ");
            return (
              <div className={`match${i === 0 ? " top" : ""}`} key={m.id}>
                <div className="match-head">
                  <span className="match-avatar" style={{ background: cat.belly }}>
                    <CatFace cat={cat} size={44} decorative />
                  </span>
                  <div className="match-who">
                    <h3 style={{ margin: 0 }}>{m.name}</h3>
                    {where && <span className="meta">{where}</span>}
                  </div>
                  <div className="match-tags">
                    {i === 0 && <span className="match-tag">closest to you</span>}
                    <span className="pill ok">
                      better match than {Math.round(m.percentile * 100)}% of the room
                    </span>
                  </div>
                </div>

                <div className="grid2 match-body">
                  <div>
                    <p className="why">{m.rationale}</p>
                    {(m.shared_artists.length > 0 || m.shared_genres.length > 0 || m.signature_progression) && (
                      <div className="chips">
                        {m.shared_artists.slice(0, 4).map((a) => (
                          <span className="chip artist" key={`a-${a}`}>{a}</span>
                        ))}
                        {m.shared_genres.slice(0, 3).map((g) => (
                          <span className="chip genre" key={`g-${g}`}>{g}</span>
                        ))}
                        {m.signature_progression && (
                          <span className="chip mono" title="Their signature progression">
                            {m.signature_progression}
                          </span>
                        )}
                      </div>
                    )}
                    {m.bio && (
                      <p className="meta" style={{ margin: "0.6rem 0 0" }}>{m.bio}</p>
                    )}
                  </div>
                  <div className="match-components">
                    <Bars
                      data={Object.fromEntries(
                        Object.entries(m.components).map(([k, v]) => [COMPONENT_LABELS[k] ?? k, v]),
                      )}
                      alt={i !== 0}
                      max={5}
                    />
                  </div>
                </div>
              </div>
            );
          })}
        </>
      )}
    </div>
  );
}
