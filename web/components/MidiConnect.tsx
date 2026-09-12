"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import ChordSteps, { type Step } from "./ChordSteps";
import { identify, type Identified } from "@/lib/api";
import {
  MidiCapture, channelStats, checkSupport, filterChannels, heldNotes,
  looksLikeChordcat, noteName, suggestHarmonyChannels,
  type ChannelStats, type MidiEvent, type MidiPort, type MidiSupport,
  type RawMessage,
} from "@/lib/webmidi";

interface Props {
  /**
   * Which half of the capture flow to render. "none" renders nothing while
   * keeping the component mounted -- the MIDI connection and the captured
   * chords live in here, and unmounting to change step would discard both.
   */
  show: "connect" | "capture" | "none";
  /** Fired once a device is selected, so the next step becomes reachable. */
  onConnected?: () => void;
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

export default function MidiConnect({
  show, onConnected, onChords, onReset, busy,
}: Props) {
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
  const [traffic, setTraffic] = useState(0);
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

      // Watch every input, so a port carrying notes is visible even when it is
      // not the one selected.
      // The pill must count *every* message, not only note events. A port
      // carrying clock or controller data but no notes is a routing problem
      // worth distinguishing from a port carrying nothing at all.
      await capture.watchAllInputs(() => {
        setPorts(capture.ports());
        setTraffic(capture.traffic().count);
      });

      const preferred = found.find(looksLikeChordcat) ?? found[0];
      if (preferred) {
        setSelected(preferred.id);
        await capture.select(preferred.id);
      }

      // Pick an output too, so the progression can be played back to the device.
      const outs = capture.outputs();
      setOutputs(outs);
      const preferredOut = outs.find(looksLikeChordcat) ?? outs[0];
      if (preferredOut) {
        setOutputId(preferredOut.id);
        await capture.selectOutput(preferredOut.id);
      }
      if (preferred) onConnected?.();
      capture.subscribe((e, all) => {
        setHeld(heldNotes(all));
        setCount(all.length);
        setTraffic(capture.traffic().count);
        if (e.k === "on" && e.p !== undefined) onNoteOn(e.p);
      });
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  async function choose(id: string) {
    setSelected(id);
    try {
      await captureRef.current!.select(id);
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

  /** Begin capturing a new take, discarding anything captured before. */
  function start() {
    startOver();
    setRecording(true);
  }

  /** Throw the take away and return to idle, without starting a new capture. */
  function startOver() {
    captureRef.current!.start();
    captureRef.current!.stopPlayback();
    resetSteps();
    setHasStoppedCapture(false);
    setCount(0);
    setHeld([]);
    setPlaying(false);
    setRecording(false);
    setError("");
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

  // Step 1: choose a device. Step 2: play into it. Separate stages of the flow,
  // so only one is on screen at a time -- but the component stays mounted
  // throughout, because it owns the connection and the captured chords.
  if (show === "none") return null;

  if (show === "connect") {
    return (
      <div className="panel">
        <div className="row spread">
          <h2 style={{ margin: 0 }}>Plug in your instrument</h2>
          <span className={`pill ${connected ? "ok" : ""}`}>
            {connected
              ? `${ports.length} device${ports.length === 1 ? "" : "s"}`
              : "not connected"}
          </span>
        </div>

        {!connected ? (
          <>
            <p className="sub">
              Your browser needs permission to read MIDI. Nothing is recorded
              until you choose to start.
            </p>
            <button className="primary" onClick={connect}>
              Connect MIDI
            </button>
          </>
        ) : (
          <>
            <p className="sub" id="device-help">
              Pick the port your notes arrive on. A dot marks any port currently
              receiving.
            </p>
            <div className="row">
              <label htmlFor="midi-in">Input</label>
              <select
                id="midi-in"
                aria-describedby="device-help"
                value={selected}
                onChange={(e) => void choose(e.target.value)}
              >
                {ports.length === 0 && <option value="">No MIDI inputs found</option>}
                {ports.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name}{p.manufacturer ? ` — ${p.manufacturer}` : ""}
                    {looksLikeChordcat(p) ? "  ✓ ChordCat" : ""}
                    {p.state !== "connected" ? `  (${p.state})` : ""}
                    {p.messages > 0 ? "  ● receiving" : ""}
                  </option>
                ))}
              </select>
            </div>

            {outputs.length > 1 && (
              <div className="row" style={{ marginTop: "0.75rem" }}>
                <label htmlFor="midi-out">Play back to</label>
                <select
                  id="midi-out"
                  value={outputId}
                  onChange={(e) => {
                    setOutputId(e.target.value);
                    captureRef.current!
                      .selectOutput(e.target.value)
                      .catch((err) =>
                        setError(err instanceof Error ? err.message : String(err)),
                      );
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

            <p
              className="row"
              style={{ marginTop: "0.9rem" }}
              role="status"
              aria-live="polite"
            >
              {/* Colour alone would leave this unreadable to anyone who cannot
                  distinguish the two, so the dot is paired with a word. */}
              <span className={`signal ${traffic > 0 ? "on" : "off"}`}>
                <span className="signal-dot" aria-hidden="true" />
                {traffic > 0 ? "Receiving" : "No signal"}
              </span>
              {traffic === 0 && (
                <span className="sub" style={{ margin: 0 }}>
                  {ports.some((p) => p.messages > 0 && p.id !== selected)
                    ? `Notes are arriving on ${ports.find((p) => p.messages > 0 && p.id !== selected)?.name} — choose it above.`
                    : "Play a note to check the connection."}
                </span>
              )}
            </p>

            {ports.length === 0 && (
              <p className="sub">
                No inputs detected. Connect the ChordCat over USB-C — it needs no
                drivers — and the list will refresh on its own.
              </p>
            )}
          </>
        )}

        {error && <p className="error">{error}</p>}

      </div>
    );
  }

  return (
    <div className="panel">
      <div className="row spread">
        <h2 style={{ margin: 0 }}>Play your chords</h2>
        <span className={`pill ${recording ? "ok" : ""}`}>
          {recording ? "listening" : "not listening"}
        </span>
      </div>

      <p className="sub">
        Play one chord after another. Each is captured the moment you play it, so
        there is no need to release before the next.
      </p>

      <div className="row">
        {!recording ? (
          <>
            {hasStoppedCapture && steps.length > 0 && (
              <button className="primary" onClick={resume} disabled={!selected || busy}>
                Add more chords
              </button>
            )}
            <button
              className={steps.length > 0 ? "" : "primary"}
              onClick={steps.length > 0 ? startOver : start}
              disabled={!selected || busy}
            >
              {steps.length > 0 ? "Start over" : "Start capturing"}
            </button>
          </>
        ) : (
          <button
            className="danger"
            onClick={() => {
              flushChord();
              setRecording(false);
              setHasStoppedCapture(true);
            }}
          >
            Stop capturing
          </button>
        )}
      </div>

      <div className="live" style={{ marginTop: "0.9rem" }} role="status" aria-live="polite">
        {held.length === 0 ? (
          <span className="pill">
            {recording ? "listening — play a chord" : "idle"}
          </span>
        ) : (
          held.map((p) => <span key={p} className="note">{noteName(p)}</span>)
        )}
      </div>

      {error && <p className="error">{error}</p>}

      {(recording || steps.length > 0) && (
        <div style={{ marginTop: "1.25rem" }}>
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
              const inFlight = [...chordBuffer.current].sort((a, b) => a - b);
              flushChord();
              setRecording(false);
              setHasStoppedCapture(true);
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
    </div>
  );
}
