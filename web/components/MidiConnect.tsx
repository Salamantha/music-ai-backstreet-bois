"use client";

import { useEffect, useRef, useState } from "react";
import {
  MidiCapture, checkSupport, heldNotes, looksLikeChordcat, noteName,
  type MidiEvent, type MidiPort, type MidiSupport,
} from "@/lib/webmidi";

interface Props {
  onEvents: (events: MidiEvent[], elapsedMs: number) => void;
  busy: boolean;
}

export default function MidiConnect({ onEvents, busy }: Props) {
  const captureRef = useRef<MidiCapture | null>(null);
  // Web MIDI support cannot be determined during server rendering -- `navigator`
  // does not exist there -- so resolve it after mount. Computing it in the
  // initial state would make the server and client render different markup.
  const [support, setSupport] = useState<MidiSupport | null>(null);
  const [ports, setPorts] = useState<MidiPort[]>([]);
  const [selected, setSelected] = useState("");
  const [connected, setConnected] = useState(false);
  const [recording, setRecording] = useState(false);
  const [held, setHeld] = useState<number[]>([]);
  const [count, setCount] = useState(0);
  const [error, setError] = useState("");

  useEffect(() => {
    setSupport(checkSupport());
    const capture = new MidiCapture();
    captureRef.current = capture;
    return () => capture.disconnect();
  }, []);

  async function connect() {
    setError("");
    try {
      const capture = captureRef.current!;
      const found = await capture.connect();
      setPorts(found);
      setConnected(true);
      capture.onStateChange(() => setPorts(capture.ports()));

      const preferred = found.find(looksLikeChordcat) ?? found[0];
      if (preferred) {
        setSelected(preferred.id);
        capture.select(preferred.id);
      }
      capture.subscribe((_e, all) => {
        setHeld(heldNotes(all));
        setCount(all.length);
      });
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  function choose(id: string) {
    setSelected(id);
    try {
      captureRef.current!.select(id);
      setError("");
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  function start() {
    captureRef.current!.start();
    setCount(0);
    setHeld([]);
    setRecording(true);
  }

  function stop() {
    const capture = captureRef.current!;
    setRecording(false);
    const events = capture.snapshot();
    if (!events.length) {
      setError("No MIDI came through. Check the ChordCat is on the selected port and try playing again.");
      return;
    }
    onEvents(events, capture.elapsed());
  }

  if (support === null) {
    return (
      <div className="panel">
        <h2>MIDI input</h2>
        <p className="sub" style={{ margin: 0 }}>Checking for Web MIDI support…</p>
      </div>
    );
  }

  if (!support.supported) {
    return (
      <div className="panel">
        <h2>MIDI input</h2>
        <p className="error">{support.reason}</p>
      </div>
    );
  }

  return (
    <div className="panel">
      <div className="row spread">
        <h2 style={{ margin: 0 }}>MIDI input</h2>
        <span className={`pill ${connected ? "ok" : ""}`}>
          {connected ? `${ports.length} device${ports.length === 1 ? "" : "s"}` : "not connected"}
        </span>
      </div>

      <div className="row" style={{ marginTop: 12 }}>
        {!connected ? (
          <button className="primary" onClick={connect}>Connect MIDI</button>
        ) : (
          <>
            <select value={selected} onChange={(e) => choose(e.target.value)}>
              {ports.length === 0 && <option value="">No MIDI inputs found</option>}
              {ports.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}{p.manufacturer ? ` — ${p.manufacturer}` : ""}
                  {looksLikeChordcat(p) ? "  ✓ ChordCat" : ""}
                </option>
              ))}
            </select>
            {!recording ? (
              <button className="primary" onClick={start} disabled={!selected || busy}>
                Start recording
              </button>
            ) : (
              <button className="danger" onClick={stop}>
                Stop &amp; analyse ({count} events)
              </button>
            )}
          </>
        )}
      </div>

      {connected && (
        <div style={{ marginTop: 14 }}>
          <div className="live">
            {held.length === 0 ? (
              <span className="pill">
                {recording ? "recording — play a progression" : "idle"}
              </span>
            ) : (
              held.map((p) => <span key={p} className="note">{noteName(p)}</span>)
            )}
          </div>
        </div>
      )}

      {error && <p className="error" style={{ marginBottom: 0 }}>{error}</p>}

      {connected && ports.length === 0 && (
        <p className="sub" style={{ margin: "10px 0 0" }}>
          No inputs detected. Connect the ChordCat over USB-C and it should appear
          without drivers; the list refreshes automatically.
        </p>
      )}
    </div>
  );
}
