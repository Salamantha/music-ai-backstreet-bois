"use client";

interface Props {
  /** Genre -> how many matched songs carry it, before filtering. */
  available: Record<string, number>;
  selected: string[];
  onChange: (genres: string[]) => void;
  busy: boolean;
}

export default function GenreFilter({ available, selected, onChange, busy }: Props) {
  const entries = Object.entries(available).sort((a, b) => b[1] - a[1]);
  if (entries.length === 0) return null;

  const active = new Set(selected);

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
            Show all genres
          </button>
        )}
      </div>

      <p className="sub" style={{ margin: "8px 0 10px" }}>
        {selected.length === 0
          ? "Showing every match. Pick genres to narrow the songs — and the musicians you get matched with."
          : `Keeping only ${selected.join(", ")}. Songs with no known genre are excluded while a filter is on.`}
      </p>

      <div className="keys">
        {entries.map(([genre, count]) => {
          const on = active.has(genre);
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
              }}
            >
              {genre}
              <span style={{ opacity: 0.55, marginLeft: 6 }}>{count}</span>
            </button>
          );
        })}
      </div>
    </div>
  );
}
