"use client";

/**
 * ChordCat Voice — the accessibility layer described in the README.
 *
 * A deliberately separate route, like /helper: this is a screen-reader-first
 * page meant to run alongside the Chordcat on stage, not inside the matching
 * wizard's step flow.
 */

import { useState } from "react";
import { useChordcatVoice } from "@/hooks/useChordcatVoice";
import { noteName } from "@/lib/webmidi";

const KEYS = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"];

export default function VoicePage() {
  const [keyTonic, setKeyTonic] = useState("C");
  const [mode, setMode] = useState("major");
  const [bpm, setBpm] = useState(100);

  const v = useChordcatVoice({ key: keyTonic, mode, bpm });
  const listening = v.status === "listening";

  return (
    <main className="voice">
      <h1>ChordCat Voice</h1>
      <p className="sub">
        Announces every chord you play, suggests what comes next, and turns a
        hummed melody into chords sent back to the device. Built for a blind
        or low-vision musician using a Chordcat, which has no speech output of
        its own.
      </p>

      <div className="panel">
        <div className="row spread">
          <div className="row">
            <label className="join-field">
              <span className="sub" style={{ margin: 0 }}>Key</span>
              <select
                value={keyTonic}
                onChange={(e) => setKeyTonic(e.target.value)}
                disabled={listening}
              >
                {KEYS.map((k) => <option key={k} value={k}>{k}</option>)}
              </select>
            </label>
            <label className="join-field">
              <span className="sub" style={{ margin: 0 }}>Mode</span>
              <select
                value={mode}
                onChange={(e) => setMode(e.target.value)}
                disabled={listening}
              >
                <option value="major">Major</option>
                <option value="minor">Minor</option>
              </select>
            </label>
            <label className="join-field">
              <span className="sub" style={{ margin: 0 }}>BPM</span>
              <input
                type="number"
                min={40}
                max={220}
                value={bpm}
                onChange={(e) => setBpm(Number(e.target.value) || 100)}
                className="join-input"
                style={{ width: "5rem" }}
                disabled={listening}
              />
            </label>
          </div>

          <button
            className={listening ? "danger" : "primary"}
            onClick={() => void (listening ? v.stop() : v.start())}
            disabled={v.status === "connecting"}
          >
            {v.status === "connecting" ? "Connecting…" : listening ? "Stop" : "Start"}
          </button>
        </div>

        <div className="row" style={{ marginTop: "0.9rem" }}>
          <span className={`signal ${listening ? "on" : "off"}`}>
            <span className="signal-dot" aria-hidden="true" />
            {v.deviceName ?? "Not connected"}
          </span>
          {v.humming && <span className="pill ok">Listening to your hum…</span>}
        </div>

        {v.error && (
          <p className="error" role="alert" style={{ marginTop: "0.75rem", marginBottom: 0 }}>
            {v.error}
          </p>
        )}
      </div>

      {listening && (
        <div className="panel">
          <h2>Keyboard</h2>
          <p className="sub" style={{ marginBottom: 0 }}>
            <span className="mono">S</span> suggestion &middot;{" "}
            <span className="mono">M</span> song match &middot;{" "}
            <span className="mono">P</span> repeat progression &middot;{" "}
            <span className="mono">H</span> hold to hum &middot;{" "}
            <span className="mono">Esc</span> stop speaking
          </p>
        </div>
      )}

      <div role="status" aria-live="polite" className="panel">
        <h2>What you played</h2>
        {v.progression.length === 0 ? (
          <p className="sub" style={{ margin: 0 }}>Nothing yet.</p>
        ) : (
          <div className="chips">
            {v.progression.map((sym, i) => (
              <span key={i} className="chip mono">{sym}</span>
            ))}
          </div>
        )}
        {v.heldNotes.length > 0 && (
          <div className="live" style={{ marginTop: "0.6rem" }}>
            {v.heldNotes.map((n, i) => (
              <span key={i} className="note">{noteName(n)}</span>
            ))}
          </div>
        )}
        <div className="row" style={{ marginTop: "0.75rem" }}>
          <button onClick={v.announceProgression} disabled={!listening}>
            Repeat progression
          </button>
          <button onClick={v.clearProgression} disabled={!listening}>
            Clear
          </button>
        </div>
      </div>

      <div className="panel" aria-live="polite">
        <h2>Suggestions</h2>
        {v.suggestions.length === 0 ? (
          <p className="sub" style={{ margin: 0 }}>Play a chord to get a suggestion.</p>
        ) : (
          <div className="chips">
            {v.suggestions.map((s) => (
              <span key={s.degree} className="chip">
                {s.symbol} <span className="sub" style={{ margin: 0 }}>
                  {Math.round(s.probability * 100)}%
                </span>
              </span>
            ))}
          </div>
        )}
        <button
          onClick={v.announceSuggestion}
          disabled={!listening}
          style={{ marginTop: "0.75rem" }}
        >
          Speak suggestion
        </button>
      </div>

      <div className="panel" aria-live="polite">
        <h2>Song matches</h2>
        {v.songs.length === 0 ? (
          <p className="sub" style={{ margin: 0 }}>No match yet.</p>
        ) : (
          <ul className="note-list" style={{ color: "var(--text)" }}>
            {v.songs.slice(0, 5).map((s, i) => (
              <li key={i}>
                <a href={s.url} target="_blank" rel="noreferrer">
                  {s.artist} &mdash; {s.song}
                </a>
                <span className="sub"> ({s.section})</span>
              </li>
            ))}
          </ul>
        )}
        <button
          onClick={v.announceSongMatch}
          disabled={!listening}
          style={{ marginTop: "0.75rem" }}
        >
          Speak song match
        </button>
      </div>

      <div className="panel">
        <h2>Hum a melody</h2>
        <p className="sub">
          Hold <span className="mono">H</span> and hum. Release to harmonise
          and send the chords back to the Chordcat.
        </p>
        {v.humNotes.length > 0 && (
          <div className="live">
            {v.humNotes.map((n, i) => (
              <span key={i} className="note">{noteName(n.midi)}</span>
            ))}
          </div>
        )}
        {v.lastHarmonisation && (
          <div className="row" style={{ marginTop: "0.6rem" }}>
            {v.lastHarmonisation.chords.length === 0 ? (
              <span className="sub">Couldn&rsquo;t find a fit that time.</span>
            ) : (
              v.lastHarmonisation.chords.map((c, i) => (
                <span key={i} className="chip mono">{c.symbol}</span>
              ))
            )}
          </div>
        )}
      </div>
    </main>
  );
}
