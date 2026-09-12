"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import ChordSteps, { type Step } from "./ChordSteps";
import MidiMonitor from "./MidiMonitor";
import { identify, type Identified } from "@/lib/api";
import {
  MidiCapture, channelStats, checkSupport, filterChannels, heldNotes,
  looksLikeChordcat, noteName, suggestHarmonyChannels,
  type ChannelStats, type MidiEvent, type MidiPort, type MidiSupport,
  type RawMessage,
} from "@/lib/webmidi";

export type CaptureMode = "steps" | "continuous";

interface Props {
  onEvents: (events: MidiEvent[], elapsedMs: number) => void;
  onChords: (steps: { pitches: number[]; duration_ms?: number }[]) => void;
  busy: boolean;
}

/** A held chord is committed once every note has been released. */
const RELEASE_COMMIT_MS = 90;
/** Wait for the voicing to settle before asking the server what it is. */
const IDENTIFY_DEBOUNCE_MS = 120;
const MIN_NOTES_PER_STEP = 2;

export default function MidiConnect({ onEvents, onChords, busy }: Props) {
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

  const [mode, setMode] = useState<CaptureMode>("steps");
  const [steps, setSteps] = useState<Step[]>([]);
  const [pending, setPending] = useState<number[]>([]);
  const [live, setLive] = useState<Identified | null>(null);
  const [hasCapture, setHasCapture] = useState(false);

  // The MIDI subscription is registered once, so its closure would capture
  // stale state. Everything the handler reads lives in a ref.
  const modeRef = useRef<CaptureMode>("steps");
  const recordingRef = useRef(false);
  const pendingRef = useRef<number[]>([]);
  const identifyTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const commitTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const nextId = useRef(1);

  useEffect(() => { modeRef.current = mode; }, [mode]);
  useEffect(() => { recordingRef.current = recording; }, [recording]);

  const commitPending = useCallback(() => {
    const pitches = pendingRef.current;
    pendingRef.current = [];
    setPending([]);
    setLive(null);
    if (pitches.length < MIN_NOTES_PER_STEP) return;
    setHasCapture(true);
    // Identify asynchronously; the step appears immediately either way, so a
    // slow or failed lookup never costs the player their chord.
    const id = nextId.current++;
    setSteps((prev) => [...prev, { id, pitches, chord: null }]);
    identify(pitches)
      .then((chord) =>
        setSteps((prev) =>
          prev.map((s) => (s.id === id ? { ...s, chord } : s)),
        ),
      )
      .catch(() => undefined);
  }, []);

  const onHeldChange = useCallback(
    (held: number[]) => {
      if (modeRef.current !== "steps" || !recordingRef.current) return;

      if (commitTimer.current) clearTimeout(commitTimer.current);

      if (held.length === 0) {
        // Everything released. Wait a moment first: the ChordCat staggers its
        // note-offs by a few ms, and a re-voicing can briefly pass through zero.
        commitTimer.current = setTimeout(commitPending, RELEASE_COMMIT_MS);
        return;
      }

      // Keep the fullest voicing seen while this chord was held, so a chord
      // whose notes land a few ms apart is captured whole rather than clipped.
      if (held.length >= pendingRef.current.length) {
        pendingRef.current = held;
        setPending(held);
      }

      if (identifyTimer.current) clearTimeout(identifyTimer.current);
      identifyTimer.current = setTimeout(() => {
        const current = pendingRef.current;
        if (current.length >= MIN_NOTES_PER_STEP) {
          identify(current).then(setLive).catch(() => setLive(null));
        }
      }, IDENTIFY_DEBOUNCE_MS);
    },
    [commitPending],
  );

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
        const currentlyHeld = heldNotes(all);
        setHeld(currentlyHeld);
        setCount(all.length);
        if (all.length > 0) setHasCapture(true);
        onHeldChange(currentlyHeld);
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

  function resetSteps() {
    setSteps([]);
    setPending([]);
    setLive(null);
    pendingRef.current = [];
    setHasCapture(false);
  }

  /** Begin a new take, discarding anything captured before. */
  function start() {
    captureRef.current!.start();
    resetSteps();
    setCount(0);
    setHeld([]);
    setStats([]);
    setRecent([]);
    setTouchedChannels(false);
    setRecording(true);
  }

  /** Carry on adding to the take already captured. */
  function resume() {
    captureRef.current!.resume();
    setHeld([]);
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
              <>
                {hasCapture && (
                  <button className="primary" onClick={resume} disabled={!selected || busy}>
                    {mode === "steps"
                      ? `Add more chords (${steps.length} so far)`
                      : `Continue recording (${count} events)`}
                  </button>
                )}
                <button
                  className={hasCapture ? "" : "primary"}
                  onClick={start}
                  disabled={!selected || busy}
                >
                  {hasCapture
                    ? "Start over"
                    : mode === "steps" ? "Start capturing" : "Start recording"}
                </button>
              </>
            ) : mode === "steps" ? (
              <button
                className="danger"
                onClick={() => {
                  // Flush a chord still being held, so the last one is not lost.
                  if (pendingRef.current.length >= MIN_NOTES_PER_STEP) commitPending();
                  setRecording(false);
                }}
              >
                Stop capturing
              </button>
            ) : (
              <button className="danger" onClick={stop}>
                Stop &amp; analyse ({count} events)
              </button>
            )}
            <span className="row" style={{ gap: 4, marginLeft: "auto" }}>
              <button
                onClick={() => setMode("steps")}
                disabled={recording}
                style={{
                  padding: "6px 11px", fontSize: 13,
                  borderColor: mode === "steps" ? "var(--accent)" : undefined,
                }}
                title="Play one chord at a time (Chord Cruiser)"
              >
                Chord by chord
              </button>
              <button
                onClick={() => setMode("continuous")}
                disabled={recording}
                style={{
                  padding: "6px 11px", fontSize: 13,
                  borderColor: mode === "continuous" ? "var(--accent)" : undefined,
                }}
                title="Record a continuous performance and segment it"
              >
                Continuous
              </button>
            </span>
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

      {mode === "steps" && (recording || steps.length > 0) && (
        <div style={{ marginTop: 16, marginLeft: -18, marginRight: -18 }}>
          <ChordSteps
            steps={steps}
            pending={pending}
            live={live}
            busy={busy}
            onRemove={(id) => setSteps((prev) => prev.filter((s) => s.id !== id))}
            onClear={resetSteps}
            onAnalyse={() =>
              onChords(steps.map((s) => ({ pitches: s.pitches, duration_ms: 600 })))
            }
          />
        </div>
      )}

      {mode === "continuous" && (stats.length > 0 || recent.length > 0) && (
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
