"use client";

import { DRUM_CHANNEL, noteName, type ChannelStats, type RawMessage } from "@/lib/webmidi";

interface Props {
  stats: ChannelStats[];
  recent: RawMessage[];
  selected: Set<number>;
  onToggle: (channel: number) => void;
  totalEvents: number;
  onDownload: () => void;
}

export default function MidiMonitor({
  stats, recent, selected, onToggle, totalEvents, onDownload,
}: Props) {
  if (stats.length === 0 && recent.length === 0) return null;

  const drums = stats.find((s) => s.channel === DRUM_CHANNEL);
  const excluded = stats.filter((s) => !selected.has(s.channel));
  const keptNotes = stats
    .filter((s) => selected.has(s.channel))
    .reduce((n, s) => n + s.noteOns, 0);

  return (
    <div className="panel">
      <div className="row spread">
        <h2 style={{ margin: 0 }}>MIDI monitor</h2>
        <span className="row" style={{ gap: 8 }}>
          <span className="pill">{totalEvents} events</span>
          <button onClick={onDownload} style={{ padding: "5px 11px", fontSize: 13 }}>
            Download take
          </button>
        </span>
      </div>

      <p className="sub" style={{ margin: "8px 0 10px" }}>
        The ChordCat streams every running sequencer track at once. Only the
        chord track should feed the analysis — merging a melody or bass line into
        it produces confident nonsense. &ldquo;Notes per onset&rdquo; is the giveaway:
        harmony lands several notes at the same instant, a melody lands one.
      </p>

      <table>
        <thead>
          <tr>
            <th style={{ width: 30 }}></th>
            <th>Ch</th><th>Note ons</th><th>Range</th>
            <th>Notes per onset</th><th>Reads as</th>
          </tr>
        </thead>
        <tbody>
          {stats.map((s) => {
            const isDrum = s.channel === DRUM_CHANNEL;
            const poly = s.modalGroupSize >= 3;
            return (
              <tr key={s.channel} style={{ opacity: selected.has(s.channel) ? 1 : 0.45 }}>
                <td>
                  <input
                    type="checkbox"
                    checked={selected.has(s.channel)}
                    onChange={() => onToggle(s.channel)}
                    aria-label={`use channel ${s.channel}`}
                  />
                </td>
                <td className="mono">{s.channel}{isDrum ? " ⚠" : ""}</td>
                <td className="mono">{s.noteOns}</td>
                <td className="mono">
                  {s.noteOns ? `${noteName(s.lowPitch)}–${noteName(s.highPitch)}` : "—"}
                </td>
                <td className="mono">
                  {s.modalGroupSize}
                  <span style={{ color: "var(--muted)" }}>
                    {" "}({Math.round(s.chordalRatio * 100)}% chordal)
                  </span>
                </td>
                <td style={{ color: "var(--muted)" }}>
                  {isDrum ? "percussion (GM ch10)"
                    : poly ? `chords (${s.modalGroupSize}-note voicings)`
                    : s.modalGroupSize === 2 ? "dyads"
                    : "single notes — melody, bass or perc"}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>

      {drums && selected.has(DRUM_CHANNEL) && (
        <p className="error" style={{ marginBottom: 0 }}>
          Channel 10 is General MIDI percussion. Including it will wreck chord
          identification — its notes are drum sounds, not pitches.
        </p>
      )}

      {excluded.length > 0 && (
        <p className="sub" style={{ margin: "10px 0 0" }}>
          Excluding channel{excluded.length > 1 ? "s" : ""}{" "}
          {excluded.map((s) => s.channel).join(", ")} — analysing {keptNotes} note-ons.
        </p>
      )}

      {recent.length > 0 && (
        <details style={{ marginTop: 12 }}>
          <summary style={{ cursor: "pointer", color: "var(--muted)", fontSize: 13 }}>
            Raw messages (last {recent.length})
          </summary>
          <div
            className="mono"
            style={{
              maxHeight: 200, overflowY: "auto", marginTop: 8, fontSize: 12,
              background: "var(--panel-2)", borderRadius: 8, padding: 10,
            }}
          >
            {recent.slice(-60).reverse().map((m, i) => (
              <div key={i} style={{ color: "var(--muted)" }}>
                {m.t.toFixed(0).padStart(7)}ms  ch{String(m.channel).padStart(2)}{" "}
                {m.type.padEnd(14)}{" "}
                [{m.bytes.map((b) => b.toString(16).padStart(2, "0")).join(" ")}]
                {m.bytes.length >= 2 && /^note/.test(m.type)
                  ? `  ${noteName(m.bytes[1])}`
                  : ""}
              </div>
            ))}
          </div>
        </details>
      )}
    </div>
  );
}
