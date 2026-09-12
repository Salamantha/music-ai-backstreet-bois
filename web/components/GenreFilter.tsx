"use client";

interface Props {
  /** Every genre that can be chosen, whether or not anything matched yet. */
  options: string[];
  /** Genre -> how many matched songs carry it. Empty before the first analysis. */
  counts: Record<string, number>;
  selected: string[];
  onChange: (genres: string[]) => void;
  /** True once results exist, so counts can be shown and zeroes dimmed. */
  hasResults: boolean;
  busy: boolean;
}

export default function GenreFilter({
  options, counts, selected, onChange, hasResults, busy,
}: Props) {
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
    <div className="panel">
      <div className="row spread">
        <h2 style={{ margin: 0 }}>Genres</h2>
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

      <p className="sub" style={{ margin: "8px 0 10px" }}>
        {selected.length === 0
          ? hasResults
            ? "Showing every match. Pick genres to narrow the songs — and the musicians you get matched with."
            : "Optional. Pick what you play and the search will keep to it — songs, artists and the musicians you get matched with."
          : `Keeping only ${selected.join(", ")}. Songs with no known genre are excluded while a genre is chosen.`}
      </p>

      <div className="keys">
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
