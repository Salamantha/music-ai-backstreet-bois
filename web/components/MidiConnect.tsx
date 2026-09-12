"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import ChordSteps, { type Step } from "./ChordSteps";
import { identify, type Identified } from "@/lib/api";
import { DEMOS } from "@/lib/demo";
import {
  MidiCapture, channelStats, checkSupport, filterChannels, heldNotes,
  looksLikeChordcat, noteName, suggestHarmonyChannels,
  type ChannelStats, type MidiEvent, type MidiPort, type MidiSupport,
  type RawMessage,
} from "@/lib/webmidi";

interface Props {
  onChords: (steps: { pitches: number[]; duration_ms?: number }[]) => void;
  /** Discard the analysis on screen, because it no longer describes anything
   *  the user can see -- the progression it came from has been cleared. */
  onReset: () => void;
  busy: boolean;
}

/**
 * How long after a chord's first note we keep listening for the rest of it.
 *
 * The ChordCat fires every note of a chord within a millisecond or two, and a
 * hand on a keyboard spreads them by a few tens of milliseconds. Once this
 * window closes the chord is known, so it commits immediately. Waiting for
 * release instead would mean holding each chord to the end before the next
 * could be played, which is not how anyone plays a progression.
 */
const ONSET_WINDOW_MS = 70;
const MIN_NOTES_PER_STEP = 2;

export default function MidiConnect({ onChords, onReset, busy }: Props) {
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

  const [steps, setSteps] = useState<Step[]>([]);
  const [pending, setPending] = useState<number[]>([]);
  const [live, setLive] = useState<Identified | null>(null);
  // True only once a capture has been started and then stopped. MIDI can arrive
  // before the user presses Start -- the device streams whenever it is playing --
  // so "has any events" is not the same thing as "has a capture to add to".
  const [hasStoppedCapture, setHasStoppedCapture] = useState(false);
  const [outputs, setOutputs] = useState<MidiPort[]>([]);
  const [outputId, setOutputId] = useState("");
  const [playing, setPlaying] = useState(false);
  const playTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  // The MIDI subscription is registered once, so its closure would capture
  // stale state. Everything the handler reads lives in a ref.
  const recordingRef = useRef(false);
  /** Notes gathered since the current onset window opened. */
  const chordBuffer = useRef<number[]>([]);
  const onsetTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const nextId = useRef(1);

  useEffect(() => { recordingRef.current = recording; }, [recording]);

  /** Add a finished chord to the progression, identifying it in the background. */
  const commitChord = useCallback((pitches: number[]) => {
    if (pitches.length < MIN_NOTES_PER_STEP) return;
    const id = nextId.current++;
    // The block appears at once; a slow or failed lookup only leaves its name
    // blank for a moment, it never costs the player the chord.
    setSteps((prev) => [...prev, { id, pitches, chord: null }]);
    identify(pitches)
      .then((chord) =>
        setSteps((prev) => prev.map((s) => (s.id === id ? { ...s, chord } : s))),
      )
      .catch(() => undefined);
  }, []);

  /** Close the current onset window and commit whatever it gathered. */
  const flushChord = useCallback(() => {
    if (onsetTimer.current) {
      clearTimeout(onsetTimer.current);
      onsetTimer.current = null;
    }
    const pitches = [...chordBuffer.current].sort((a, b) => a - b);
    chordBuffer.current = [];
    setPending([]);
    setLive(null);
    commitChord(pitches);
  }, [commitChord]);

  /**
   * Handle one note-on.
   *
   * The first note opens a window; anything arriving inside it belongs to the
   * same chord. When the window closes the chord commits, so the next one can
   * be played straight away -- and may overlap the previous, since only
   * note-ons are considered here.
   */
  const onNoteOn = useCallback(
    (pitch: number) => {
      if (!recordingRef.current) return;

      if (onsetTimer.current === null) {
        chordBuffer.current = [pitch];
        setPending([pitch]);
        onsetTimer.current = setTimeout(flushChord, ONSET_WINDOW_MS);
      } else if (!chordBuffer.current.includes(pitch)) {
        chordBuffer.current.push(pitch);
        setPending([...chordBuffer.current].sort((a, b) => a - b));
      }
    },
    [flushChord],
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
      capture.onStateChange(() => {
        setPorts(capture.ports());
        setOutputs(capture.outputs());
      });

      const preferred = found.find(looksLikeChordcat) ?? found[0];
      if (preferred) {
        setSelected(preferred.id);
        capture.select(preferred.id);
      }

      // Pick an output too, so the progression can be played back to the device.
      const outs = capture.outputs();
      setOutputs(outs);
      const preferredOut = outs.find(looksLikeChordcat) ?? outs[0];
      if (preferredOut) {
        setOutputId(preferredOut.id);
        capture.selectOutput(preferredOut.id);
      }
      capture.subscribe((e, all) => {
        setHeld(heldNotes(all));
        setCount(all.length);
        if (e.k === "on" && e.p !== undefined) onNoteOn(e.p);
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

  function resetSteps() {
    setSteps([]);
    setPending([]);
    setLive(null);
    chordBuffer.current = [];
    if (onsetTimer.current) {
      clearTimeout(onsetTimer.current);
      onsetTimer.current = null;
    }
    onReset();
  }

  /** Begin a new take, discarding anything captured before. */
  function start() {
    captureRef.current!.start();
    resetSteps();
    setHasStoppedCapture(false);
    setCount(0);
    setHeld([]);
    setRecording(true);
  }

  /** Carry on adding to the take already captured. */
  function resume() {
    captureRef.current!.resume();
    setHeld([]);
    setRecording(true);
  }

  function playBack() {
    const capture = captureRef.current!;
    if (playing) {
      capture.stopPlayback();
      if (playTimer.current) clearTimeout(playTimer.current);
      setPlaying(false);
      return;
    }
    try {
      const total = capture.play(steps.map((s) => s.pitches));
      setPlaying(true);
      playTimer.current = setTimeout(() => setPlaying(false), total + 200);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  /** Load a demo progression, so the capture UI can be exercised with no
   *  hardware attached. In step mode it fills the chord list; in continuous
   *  mode it feeds the same synthetic note stream the segmenter would see. */
  function loadDemo(demoId: string) {
    const demo = DEMOS.find((d) => d.id === demoId);
    if (!demo) return;
    resetSteps();
    setHasStoppedCapture(true);
    demo.chords.forEach((pitches) => {
      const id = nextId.current++;
      setSteps((prev) => [...prev, { id, pitches, chord: null }]);
      identify(pitches)
        .then((chord) =>
          setSteps((prev) => prev.map((s) => (s.id === id ? { ...s, chord } : s))),
        )
        .catch(() => undefined);
    });
  }

  /** Move a captured chord to a different position in the progression. */
  function reorderStep(from: number, to: number) {
    setSteps((prev) => {
      if (from === to || from < 0 || from >= prev.length) return prev;
      if (to < 0 || to >= prev.length) return prev;
      const next = [...prev];
      const [moved] = next.splice(from, 1);
      next.splice(to, 0, moved);
      return next;
    });
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
                {/* Only offer to resume when there is something to resume. A
                    capture that was stopped without producing a chord has
                    nothing to add to, so it reads as a fresh start. */}
                {hasStoppedCapture && steps.length > 0 && (
                  <button className="primary" onClick={resume} disabled={!selected || busy}>
                    Add more chords ({steps.length} so far)
                  </button>
                )}
                <button
                  className={steps.length > 0 ? "" : "primary"}
                  onClick={start}
                  disabled={!selected || busy}
                >
                  {steps.length > 0 ? "Start over" : "Start capturing"}
                </button>
              </>
            ) : (
              <button
                className="danger"
                onClick={() => {
                  // Commit a chord still inside its onset window, so the last
                  // one played is not lost to the stop.
                  flushChord();
                  setRecording(false);
                  setHasStoppedCapture(true);
                }}
              >
                Stop capturing
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

      {!recording && (
        <div style={{ marginTop: 14 }}>
          <p className="sub" style={{ margin: "0 0 8px" }}>
            No ChordCat to hand? Load a progression to try the interface.
          </p>
          <div className="keys">
            {DEMOS.map((d) => (
              <button
                key={d.id}
                onClick={() => loadDemo(d.id)}
                disabled={busy}
                title={d.hint}
                style={{ fontSize: 13 }}
              >
                {d.label}
              </button>
            ))}
          </div>
        </div>
      )}

      {(recording || steps.length > 0) && (
        <div style={{ marginTop: 16, marginLeft: -18, marginRight: -18 }}>
          <ChordSteps
            steps={steps}
            pending={pending}
            live={live}
            busy={busy}
            onRemove={(id) => setSteps((prev) => prev.filter((s) => s.id !== id))}
            onReorder={reorderStep}
            onClear={resetSteps}
            onPlay={playBack}
            canPlay={connected && outputs.length > 0}
            playing={playing}
            onAnalyse={() => {
              // Analysing ends the take. Without this, anything played while
              // the results load would quietly append to the progression that
              // was just analysed.
              const inFlight = [...chordBuffer.current].sort((a, b) => a - b);
              flushChord();
              setRecording(false);
              setHasStoppedCapture(true);

              // A chord still inside its onset window has not reached `steps`
              // yet, so include it explicitly rather than losing it.
              const captured = steps.map((s) => ({
                pitches: s.pitches,
                duration_ms: 600,
              }));
              if (inFlight.length >= MIN_NOTES_PER_STEP) {
                captured.push({ pitches: inFlight, duration_ms: 600 });
              }
              onChords(captured);
            }}
          />
        </div>
      )}


      {connected && outputs.length > 1 && (
        <div className="row" style={{ marginTop: 10, gap: 8 }}>
          <span className="sub" style={{ margin: 0 }}>Play back to</span>
          <select
            value={outputId}
            onChange={(e) => {
              setOutputId(e.target.value);
              try {
                captureRef.current!.selectOutput(e.target.value);
              } catch (err) {
                setError(err instanceof Error ? err.message : String(err));
              }
            }}
          >
            {outputs.map((o) => (
              <option key={o.id} value={o.id}>
                {o.name}{looksLikeChordcat(o) ? "  ✓ ChordCat" : ""}
              </option>
            ))}
          </select>
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
