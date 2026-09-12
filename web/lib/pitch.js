/**
 * pitch.js — microphone in, discrete sung notes out.
 *
 * Requires: npm i pitchy
 *
 * Deliberately NOT using CREPE. A browser CREPE model is a few megabytes and
 * adds inference latency to every frame, to solve a problem that autocorrelation
 * handles fine for a single monophonic voice. If accuracy ever becomes the
 * bottleneck, swap findPitch() for CREPE behind the same interface — nothing
 * downstream of this file needs to change.
 *
 * The three things that make raw pitch output usable:
 *   - a clarity gate, so breath and room noise don't register,
 *   - a median filter, because the voice octave-jumps constantly,
 *   - hysteresis, so a note has to be stable for several frames before we
 *     accept that the singer actually moved.
 */

import { PitchDetector } from "pitchy";

const DEFAULTS = {
  fftSize: 2048,
  clarityThreshold: 0.9, // 0.85 if the room is loud, 0.93 if it's quiet
  minHz: 65, // ~C2
  maxHz: 1000, // ~B5
  medianWindow: 5, // odd number
  stableFrames: 3, // frames on a new pitch before we commit to it
  silenceFrames: 6, // frames below clarity before we end the note
  minNoteMs: 90, // anything shorter is a glitch, not a note
};

export function hzToMidi(hz) {
  return 69 + 12 * Math.log2(hz / 440);
}

export function midiToHz(midi) {
  return 440 * Math.pow(2, (midi - 69) / 12);
}

function median(arr) {
  const s = [...arr].sort((a, b) => a - b);
  return s[Math.floor(s.length / 2)];
}

/**
 * createPitchTracker({ onNote, onFrame, ...opts })
 *
 * onNote({ midi, startMs, durMs, cents })  fires once per completed note
 * onFrame({ midi, hz, clarity })           fires every animation frame, for UI
 *
 * Returns { start, stop, isRunning }.
 */
export function createPitchTracker({ onNote, onFrame, ...opts } = {}) {
  const cfg = { ...DEFAULTS, ...opts };

  let audioCtx = null;
  let stream = null;
  let analyser = null;
  let detector = null;
  let buffer = null;
  let raf = null;
  let running = false;

  // rolling state
  let history = [];
  let currentMidi = null;
  let candidateMidi = null;
  let candidateCount = 0;
  let noteStart = 0;
  let quietCount = 0;
  let centsAccum = [];
  let t0 = 0;

  function commitNote(endMs) {
    if (currentMidi == null) return;
    const durMs = endMs - noteStart;
    if (durMs >= cfg.minNoteMs) {
      const cents =
        centsAccum.length > 0
          ? centsAccum.reduce((a, b) => a + b, 0) / centsAccum.length
          : 0;
      onNote?.({ midi: currentMidi, startMs: noteStart, durMs, cents });
    }
    currentMidi = null;
    centsAccum = [];
  }

  function tick() {
    if (!running) return;
    raf = requestAnimationFrame(tick);

    analyser.getFloatTimeDomainData(buffer);
    const [hz, clarity] = detector.findPitch(buffer, audioCtx.sampleRate);
    const now = performance.now() - t0;

    const valid =
      clarity >= cfg.clarityThreshold && hz >= cfg.minHz && hz <= cfg.maxHz;

    if (!valid) {
      quietCount += 1;
      if (quietCount >= cfg.silenceFrames) {
        commitNote(now);
        history = [];
        candidateMidi = null;
        candidateCount = 0;
      }
      onFrame?.({ midi: null, hz: null, clarity });
      return;
    }

    quietCount = 0;
    const exact = hzToMidi(hz);
    history.push(exact);
    if (history.length > cfg.medianWindow) history.shift();
    if (history.length < cfg.medianWindow) {
      onFrame?.({ midi: null, hz, clarity });
      return;
    }

    const smoothed = median(history);
    const rounded = Math.round(smoothed);
    onFrame?.({ midi: rounded, hz, clarity });

    if (currentMidi === null) {
      currentMidi = rounded;
      noteStart = now;
      centsAccum = [(smoothed - rounded) * 100];
      candidateMidi = null;
      candidateCount = 0;
      return;
    }

    if (rounded === currentMidi) {
      centsAccum.push((smoothed - rounded) * 100);
      candidateMidi = null;
      candidateCount = 0;
      return;
    }

    // The singer appears to have moved. Require stability before believing it.
    if (rounded === candidateMidi) {
      candidateCount += 1;
    } else {
      candidateMidi = rounded;
      candidateCount = 1;
    }

    if (candidateCount >= cfg.stableFrames) {
      commitNote(now);
      currentMidi = candidateMidi;
      noteStart = now;
      centsAccum = [];
      candidateMidi = null;
      candidateCount = 0;
    }
  }

  async function start() {
    if (running) return;
    stream = await navigator.mediaDevices.getUserMedia({
      audio: {
        echoCancellation: false,
        noiseSuppression: false,
        autoGainControl: false,
      },
    });
    audioCtx = new (window.AudioContext || window.webkitAudioContext)();
    const source = audioCtx.createMediaStreamSource(stream);
    analyser = audioCtx.createAnalyser();
    analyser.fftSize = cfg.fftSize;
    source.connect(analyser);

    detector = PitchDetector.forFloat32Array(analyser.fftSize);
    buffer = new Float32Array(detector.inputLength);

    history = [];
    currentMidi = null;
    candidateMidi = null;
    candidateCount = 0;
    quietCount = 0;
    t0 = performance.now();
    running = true;
    tick();
  }

  function stop() {
    if (!running) return;
    running = false;
    cancelAnimationFrame(raf);
    commitNote(performance.now() - t0);
    stream?.getTracks().forEach((t) => t.stop());
    audioCtx?.close();
    audioCtx = null;
    stream = null;
  }

  return { start, stop, isRunning: () => running };
}

/* ---------------------------------------------------------------------- */
/* Quantising                                                              */
/* ---------------------------------------------------------------------- */

/**
 * Group raw sung notes into bars so the harmoniser has something to chew on.
 * Returns [{ index, startMs, endMs, notes: [...] }, ...]
 */
export function groupIntoBars(notes, { bpm = 100, beatsPerBar = 4 } = {}) {
  if (!notes.length) return [];
  const barMs = (60000 / bpm) * beatsPerBar;
  const totalMs = Math.max(...notes.map((n) => n.startMs + n.durMs));
  const barCount = Math.max(1, Math.ceil(totalMs / barMs));

  return Array.from({ length: barCount }, (_, i) => {
    const startMs = i * barMs;
    const endMs = startMs + barMs;
    const inBar = notes
      .filter((n) => n.startMs < endMs && n.startMs + n.durMs > startMs)
      .map((n) => ({
        ...n,
        // how much of this note actually sounds inside the bar
        weight:
          Math.min(endMs, n.startMs + n.durMs) - Math.max(startMs, n.startMs),
      }));
    return { index: i, startMs, endMs, notes: inBar };
  }).filter((b) => b.notes.length > 0);
}

/** Pitch-class histogram weighted by duration — used for key inference. */
export function pitchClassProfile(notes) {
  const profile = new Array(12).fill(0);
  for (const n of notes) profile[((n.midi % 12) + 12) % 12] += n.durMs;
  return profile;
}
