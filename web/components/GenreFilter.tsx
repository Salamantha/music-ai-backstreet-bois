"use client";

import type { Tonality } from "@/lib/api";

interface Props {
  tonality: Tonality;
  onTonality: (t: Tonality) => void;
  /** Every genre that can be chosen, whether or not anything matched yet. */
  options: string[];
  /** Genre -> how many matched songs carry it. Empty before the first analysis. */
  counts: Record<string, number>;
  selected: string[];
  onChange: (genres: string[]) => void;
  /** True once results exist, so counts can be shown and zeroes dimmed. */
  hasResults: boolean;
  busy: boolean;
  /** Render without the surrounding panel, for use inside another one. */
  bare?: boolean;
}

/* Nested inside the capture panel these sit a level deeper, and a heading
   order that skips or reverses levels is how screen-reader users lose the
   shape of a page. */

const TONALITIES: { value: Tonality; label: string; hint: string }[] = [
  { value: "any", label: "Any", hint: "Not sure — let the analysis decide" },
  { value: "major", label: "Major", hint: "Brighter, happier" },
  { value: "minor", label: "Minor", hint: "Darker, sadder" },
];

export default function GenreFilter({
  options, counts, selected, onChange, hasResults, busy, tonality, onTonality,
  bare = false,
}: Props) {
  const H = bare ? "h3" : "h2";
  const active = new Set(selected);
  if (options.length === 0) return null;

  // Before any analysis, alphabetical. Afterwards, what actually matched first.
  const entries = [...options].sort((a, b) =>
    hasResults ? (counts[b] ?? 0) - (counts[a] ?? 0) || a.localeCompare(b)
               : a.localeCompare(b),
  );

  function toggle(genre: string) {
    const next = new Set(active);
    if (next.has(genre)) next.delete(genre);
    else next.add(genre);
    onChange([...next]);
  }

  return (
    <div className={bare ? "" : "panel"}>
      <div className="row spread" style={{ marginBottom: 12 }}>
        <H style={{ margin: 0 }}>Tonality</H>
        <span className="row" style={{ gap: 4 }}>
          {TONALITIES.map((t) => (
            <button
              key={t.value}
              onClick={() => onTonality(t.value)}
              disabled={busy}
              aria-pressed={tonality === t.value}
              title={t.hint}
              style={{
                fontSize: 13,
                padding: "6px 13px",
                fontWeight: tonality === t.value ? 700 : 500,
                borderColor: tonality === t.value ? "var(--accent)" : undefined,
                color: tonality === t.value ? "var(--accent)" : undefined,
              }}
            >
              {t.label}
            </button>
          ))}
        </span>
      </div>
      <p className="sub" style={{ margin: "0 0 16px" }}>
        Major sounds bright and happy; minor sounds darker and sadder. The
        very same chords can be heard either way, so tell us which you meant
        and the matches will lean that way.
      </p>

      <div className="row spread">
        <H style={{ margin: 0 }}>Genres</H>
        {selected.length > 0 && (
          <button
            onClick={() => onChange([])}
            disabled={busy}
            style={{ padding: "5px 11px", fontSize: 13 }}
          >
            Any genre
          </button>
        )}
      </div>

      {/* No blurb while setting up -- the buttons say what they do. On the
          results step it stays, because there it explains an absence: why a
          song you expected is no longer in the list. */}
      {!bare && (
        <p className="sub" style={{ margin: "8px 0 10px" }}>
          {selected.length === 0
            ? "Showing every match. Pick genres to narrow the songs — and the musicians you get matched with."
            : `Keeping only ${selected.join(", ")}. Songs with no known genre are excluded while a genre is chosen.`}
        </p>
      )}

      {/* Without the blurb above them the pills would butt up against the
          heading, so the space it used to provide comes back explicitly. */}
      <div className="keys" style={bare ? { marginTop: "0.8rem" } : undefined}>
        {entries.map((genre) => {
          const on = active.has(genre);
          const count = counts[genre] ?? 0;
          const absent = hasResults && count === 0 && !on;
          return (
            <button
              key={genre}
              onClick={() => toggle(genre)}
              disabled={busy}
              aria-pressed={on}
              style={{
                fontSize: 13,
                fontWeight: on ? 700 : 500,
                borderColor: on ? "var(--accent)" : undefined,
                color: on ? "var(--accent)" : undefined,
                opacity: absent ? 0.4 : 1,
              }}
              title={
                hasResults && !on
                  ? `${count} matched song${count === 1 ? "" : "s"}`
                  : undefined
              }
            >
              {genre}
              {hasResults && (
                <span style={{ opacity: 0.55, marginLeft: 6 }}>{count}</span>
              )}
            </button>
          );
        })}
      </div>
    </div>
  );
}
