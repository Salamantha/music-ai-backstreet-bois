"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import ChordSteps, { type Step } from "./ChordSteps";
import { identify } from "@/lib/api";
import { createPitchTracker } from "@/lib/pitch.js";
import { harmonizeMelody as harmonizeMelodyJs } from "@/lib/harmonize.js";
import { nextDegreeProbs as nextDegreeProbsJs } from "@/lib/hooktheory.js";

/** Same reasoning as `harmonizeMelody` above: re-typed from the real shape. */
const nextDegreeProbs = nextDegreeProbsJs as unknown as (
  cp: string,
) => Promise<Record<number, number>>;
import { noteName } from "@/lib/webmidi";

interface SungNote {
  midi: number;
  startMs: number;
  durMs: number;
  cents: number;
}

interface PitchTracker {
  start: () => Promise<void>;
  stop: () => void;
  isRunning: () => boolean;
}

interface HarmonizedChord {
  bar: number;
  degree: number;
  symbol: string | null;
  notes: number[];
  confidence: number;
}

/**
 * `harmonize.js` isn't type-checked (allowJs without checkJs), and TypeScript's
 * best-effort inference over its destructured-with-defaults options parameter
 * drops `getNextProbs` (the one property with no default). Re-typed here from
 * the actual implementation rather than fighting that inference.
 */
const harmonizeMelody = harmonizeMelodyJs as unknown as (
  notes: SungNote[],
  opts: {
    bpm?: number;
    beatsPerBar?: number;
    getNextProbs?: (cp: string) => Promise<Record<number, number>>;
  },
) => Promise<{
  key: { tonic: string; mode: string; confidence: number };
  bars: unknown[];
  chords: HarmonizedChord[];
}>;

interface Props {
  /** Mirrors MidiConnect's `show`, so the two sit in the same steps without
   *  either tearing down its own state. */
  show: "connect" | "capture" | "none";
  onConnected?: () => void;
  onChords: (steps: { pitches: number[]; duration_ms?: number }[]) => void;
  onReset: () => void;
  resetToken: number;
  children?: React.ReactNode;
  next?: React.ReactNode;
  busy: boolean;
}

const BPM = 90;
const BEATS_PER_BAR = 4;
const BAR_MS = (60000 / BPM) * BEATS_PER_BAR;

export default function VoiceSing({
  show, onConnected, onChords, onReset, resetToken, children, next, busy,
}: Props) {
  const [supported, setSupported] = useState<boolean | null>(null);
  const [connected, setConnected] = useState(false);
  const [recording, setRecording] = useState(false);
  const [harmonizing, setHarmonizing] = useState(false);
  const [currentNote, setCurrentNote] = useState<string | null>(null);
  const [chords, setChords] = useState<HarmonizedChord[]>([]);
  const [steps, setSteps] = useState<Step[]>([]);
  const [error, setError] = useState("");

  const trackerRef = useRef<PitchTracker | null>(null);
  const notesRef = useRef<SungNote[]>([]);
  const nextId = useRef(1);
  const firstReset = useRef(true);

  useEffect(() => {
    setSupported(typeof navigator !== "undefined" && !!navigator.mediaDevices?.getUserMedia);
    return () => trackerRef.current?.stop();
  }, []);

  async function enableMic() {
    setError("");
    try {
      // Only to trigger/confirm the permission prompt -- the pitch tracker
      // opens its own stream when singing actually starts.
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      stream.getTracks().forEach((t) => t.stop());
      setConnected(true);
      onConnected?.();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  function resetAll() {
    trackerRef.current?.stop();
    trackerRef.current = null;
    notesRef.current = [];
    setRecording(false);
    setHarmonizing(false);
    setCurrentNote(null);
    setChords([]);
    setSteps([]);
    setError("");
  }

  const startOver = useCallback(() => {
    resetAll();
    onReset();
  }, [onReset]);

  useEffect(() => {
    if (firstReset.current) {
      firstReset.current = false;
      return;
    }
    resetAll();
    // resetAll/onReset are redefined every render; the token is the real
    // dependency, matching MidiConnect's identical pattern.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [resetToken]);

  async function start() {
    setError("");
    setChords([]);
    setSteps([]);
    notesRef.current = [];
    const tracker: PitchTracker = createPitchTracker({
      onNote: (note: SungNote) => notesRef.current.push(note),
      onFrame: ({ midi }: { midi: number | null }) =>
        setCurrentNote(midi === null ? null : noteName(midi)),
    });
    trackerRef.current = tracker;
    try {
      await tracker.start();
      setRecording(true);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  async function stopAndHarmonize() {
    trackerRef.current?.stop();
    setRecording(false);
    setCurrentNote(null);

    if (notesRef.current.length < 2) {
      setError("Didn't catch enough of that. Try singing a longer phrase.");
      return;
    }

    setHarmonizing(true);
    setError("");
    try {
      const result = await harmonizeMelody(notesRef.current, {
        bpm: BPM,
        beatsPerBar: BEATS_PER_BAR,
        getNextProbs: nextDegreeProbs,
      });
      const found: HarmonizedChord[] = result.chords;
      if (found.length === 0) {
        setError("Couldn't find chords in that melody. Try again, a bit slower.");
        return;
      }
      setChords(found);

      const built = await Promise.all(
        found.map(async (c): Promise<Step> => {
          const id = nextId.current++;
          try {
            const chord = await identify(c.notes);
            return { id, pitches: c.notes, chord };
          } catch {
            return { id, pitches: c.notes, chord: null };
          }
        }),
      );
      setSteps(built);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setHarmonizing(false);
    }
  }

  if (supported === null) return null;
  if (show === "none") return null;

  if (!supported) {
    return (
      <div className="panel">
        <h2>Sing a melody</h2>
        <p className="error">
          This browser cannot record from a microphone. Try Chrome, Firefox, or Edge.
        </p>
      </div>
    );
  }

  if (show === "connect") {
    return (
      <div className="panel">
        <div className="row spread">
          <h2 style={{ margin: 0 }}>Sing a melody</h2>
          <span className={`pill ${connected ? "ok" : ""}`}>
            {connected ? "microphone ready" : "not enabled"}
          </span>
        </div>
        {!connected ? (
          <>
            <p className="sub">
              Hum or sing a melody instead of playing a device. We listen for the
              notes and work out the chords underneath them.
            </p>
            <button className="primary" onClick={enableMic}>
              Enable microphone
            </button>
          </>
        ) : (
          <p className="sub" style={{ margin: 0 }}>
            Microphone ready — move on to sing a melody.
          </p>
        )}
        {error && <p className="error">{error}</p>}
        {next && <div className="card-nav">{next}</div>}
      </div>
    );
  }

  return (
    <div className="panel">
      <div className="row spread">
        <h2 style={{ margin: 0 }}>Sing a melody</h2>
        <span className={`pill ${recording ? "ok" : ""}`}>
          {recording ? "listening" : "not listening"}
        </span>
      </div>

      <p className="sub">
        Sing or hum a melody, a phrase is plenty. Stop when you're done and
        we'll work out the most likely chords underneath it.
      </p>

      <div className="row">
        {!recording ? (
          <button
            className={steps.length > 0 ? "" : "primary"}
            onClick={steps.length > 0 ? startOver : start}
            disabled={busy || harmonizing}
          >
            {steps.length > 0 ? "Start over" : "Start singing"}
          </button>
        ) : (
          <button className="danger" onClick={stopAndHarmonize}>
            Stop and harmonise
          </button>
        )}
      </div>

      <div className="live" style={{ marginTop: "0.9rem" }} role="status" aria-live="polite">
        {currentNote
          ? <span className="note">{currentNote}</span>
          : recording && <span className="pill">listening — sing a note</span>}
        {harmonizing && <span className="pill">working out the chords…</span>}
      </div>

      {error && <p className="error">{error}</p>}

      {steps.length > 0 && (
        <div style={{ marginTop: "1.25rem" }}>
          <ChordSteps
            steps={steps}
            pending={[]}
            live={null}
            busy={busy}
            onRemove={(id) => {
              setSteps((prev) => prev.filter((s) => s.id !== id));
              setChords((prev) => prev.filter((_, i) => steps[i]?.id !== id));
            }}
            onReorder={(from, to) =>
              setSteps((prev) => {
                if (from === to || from < 0 || from >= prev.length) return prev;
                if (to < 0 || to >= prev.length) return prev;
                const next = [...prev];
                const [moved] = next.splice(from, 1);
                next.splice(to, 0, moved);
                return next;
              })
            }
            onClear={resetAll}
            onPlay={() => {}}
            canPlay={false}
            playing={false}
            onAnalyse={() =>
              onChords(steps.map((s) => ({ pitches: s.pitches, duration_ms: BAR_MS })))
            }
          />
        </div>
      )}

      {children && <div className="setup">{children}</div>}
    </div>
  );
}
