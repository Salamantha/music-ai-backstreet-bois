"use client";

import { useEffect, useRef, useState } from "react";
import MidiMonitor from "./MidiMonitor";
import {
  MidiCapture, channelStats, checkSupport, filterChannels, heldNotes,
  looksLikeChordcat, noteName, suggestHarmonyChannels,
  type ChannelStats, type MidiEvent, type MidiPort, type MidiSupport,
  type RawMessage,
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
  const [stats, setStats] = useState<ChannelStats[]>([]);
  const [recent, setRecent] = useState<RawMessage[]>([]);
  const [channels, setChannels] = useState<Set<number>>(new Set());
  const [touchedChannels, setTouchedChannels] = useState(false);

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
        const next = channelStats(all);
        setStats(next);
        // Preselect the channels that look like harmony, but never fight the
        // user once they have made a choice of their own.
        setTouchedChannels((touched) => {
          if (!touched) setChannels(suggestHarmonyChannels(next));
          return touched;
        });
      });
      capture.subscribeRaw(() => setRecent(capture.rawMessages()));
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
    setStats([]);
    setRecent([]);
    setTouchedChannels(false);
    setRecording(true);
  }

  function toggleChannel(channel: number) {
    setTouchedChannels(true);
    setChannels((prev) => {
      const next = new Set(prev);
      if (next.has(channel)) next.delete(channel);
      else next.add(channel);
      return next;
    });
  }

  function download() {
    const capture = captureRef.current!;
    const payload = {
      captured_at: new Date().toISOString(),
      device: ports.find((p) => p.id === selected)?.name ?? "unknown",
      elapsed_ms: capture.elapsed(),
      channel_stats: channelStats(capture.snapshot()),
      events: capture.snapshot(),
      raw_tail: capture.rawMessages(),
    };
    const blob = new Blob([JSON.stringify(payload, null, 1)], {
      type: "application/json",
    });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `chordcat-take-${Date.now()}.json`;
    a.click();
    URL.revokeObjectURL(url);
  }

  function stop() {
    const capture = captureRef.current!;
    setRecording(false);
    const all = capture.snapshot();
    if (!all.length) {
      setError("No MIDI came through. Check the ChordCat is on the selected port and try playing again.");
      return;
    }
    const events = channels.size > 0 ? filterChannels(all, channels) : all;
    if (!events.length) {
      setError("Every captured channel is excluded. Tick at least one channel to analyse.");
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

      {(stats.length > 0 || recent.length > 0) && (
        <div style={{ marginTop: 16, marginLeft: -18, marginRight: -18, marginBottom: -18 }}>
          <MidiMonitor
            stats={stats}
            recent={recent}
            selected={channels}
            onToggle={toggleChannel}
            totalEvents={count}
            onDownload={download}
          />
        </div>
      )}

      {connected && ports.length === 0 && (
        <p className="sub" style={{ margin: "10px 0 0" }}>
          No inputs detected. Connect the ChordCat over USB-C and it should appear
          without drivers; the list refreshes automatically.
        </p>
      )}
    </div>
  );
}
