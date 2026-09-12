"use client";

import { useEffect, useRef, useState } from "react";

const inputStyle: React.CSSProperties = {
  font: "inherit", background: "var(--panel-2)", color: "var(--text)",
  border: "1px solid var(--line)", borderRadius: 8, padding: "9px 11px",
  width: "100%", boxSizing: "border-box",
};

/** Free-text city field with suggestions from Open-Meteo's geocoder. */
export function CityInput({
  value, onChange, placeholder = "City", id,
}: {
  value: string;
  onChange: (city: string) => void;
  placeholder?: string;
  id?: string;
}) {
  const [suggestions, setSuggestions] = useState<string[]>([]);
  const [open, setOpen] = useState(false);
  const suppressNextFetch = useRef(false);

  useEffect(() => {
    if (suppressNextFetch.current) {
      suppressNextFetch.current = false;
      return;
    }
    const query = value.trim();
    if (query.length < 2) {
      setSuggestions([]);
      return;
    }
    const controller = new AbortController();
    const timeout = setTimeout(async () => {
      try {
        const res = await fetch(
          `https://geocoding-api.open-meteo.com/v1/search?name=${encodeURIComponent(query)}&count=5&language=en&format=json`,
          { signal: controller.signal },
        );
        const data = await res.json();
        const results = (data.results ?? []) as {
          name: string; admin1?: string; country?: string;
        }[];
        const labels = results.map((r) =>
          [r.name, r.admin1, r.country].filter(Boolean).join(", "),
        );
        setSuggestions([...new Set(labels)]);
        setOpen(true);
      } catch {
        // aborted or offline; keep whatever the user typed
      }
    }, 300);
    return () => {
      controller.abort();
      clearTimeout(timeout);
    };
  }, [value]);

  function pick(label: string) {
    suppressNextFetch.current = true;
    onChange(label);
    setOpen(false);
    setSuggestions([]);
  }

  return (
    <div style={{ position: "relative", flex: 1 }}>
      <input
        id={id}
        className="mono"
        style={inputStyle}
        placeholder={placeholder}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        onFocus={() => suggestions.length > 0 && setOpen(true)}
        onBlur={() => setTimeout(() => setOpen(false), 100)}
        autoComplete="off"
      />
      {open && suggestions.length > 0 && (
        <ul
          style={{
            position: "absolute", top: "calc(100% + 4px)", left: 0, right: 0,
            background: "var(--panel-2)", border: "1px solid var(--line)",
            borderRadius: 8, listStyle: "none", margin: 0, padding: 4,
            zIndex: 10, maxHeight: 200, overflowY: "auto",
          }}
        >
          {suggestions.map((s) => (
            <li key={s}>
              <button
                type="button"
                onMouseDown={(e) => e.preventDefault()}
                onClick={() => pick(s)}
                style={{
                  font: "inherit", background: "none", border: "none",
                  color: "var(--text)", width: "100%", textAlign: "left",
                  padding: "6px 8px", borderRadius: 6, cursor: "pointer",
                }}
                onMouseEnter={(e) => (e.currentTarget.style.background = "var(--panel)")}
                onMouseLeave={(e) => (e.currentTarget.style.background = "none")}
              >
                {s}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
