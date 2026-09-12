/**
 * chords.js — MIDI notes in, chord names and Hooktheory degrees out.
 *
 * Requires: npm i tonal
 *
 * Two jobs:
 *   1. Collect simultaneous note-ons into a chord and name it.
 *   2. Convert that chord into the degree number Hooktheory's `cp` param wants.
 *
 * On the second job, note the big simplification: Hooktheory numbers everything
 * relative to the MAJOR scale ("pretend every song were transposed to C"), so a
 * minor-key song is expressed in its relative major. We convert minor keys to
 * the relative major before computing degrees. This matches how Hooktheory's own
 * Trends page behaves, but it means a piece in A minor reports vi–IV–I–V rather
 * than i–VI–III–VII. Say that out loud if a judge asks; don't try to fix it
 * tonight.
 */

import { Chord, Note } from "tonal";

/** Semitones above the major tonic -> scale degree. Anything else is chromatic. */
const SEMITONE_TO_DEGREE = { 0: 1, 2: 2, 4: 3, 5: 4, 7: 5, 9: 6, 11: 7 };

/** Expected triad quality on each degree of a major scale. */
const DIATONIC_QUALITY = {
  1: "major",
  2: "minor",
  3: "minor",
  4: "major",
  5: "major",
  6: "minor",
  7: "diminished",
};

const ROMAN = { 1: "I", 2: "ii", 3: "iii", 4: "IV", 5: "V", 6: "vi", 7: "vii" };

/** Semitone offsets of the major scale from its tonic. */
export const MAJOR_SCALE_OFFSETS = [0, 2, 4, 5, 7, 9, 11];

/** A minor key shares its chord pool with the major a minor third above. */
export function relativeMajor(tonic, mode) {
  if (!tonic) return null;
  return mode === "minor" ? Note.transpose(tonic, "3m") : tonic;
}

/**
 * Convert a chord symbol to a Hooktheory degree in the given key.
 * Returns { degree, roman, diatonic, quality } or null if it can't be expressed.
 *
 * `diatonic: false` means the root sits on a scale degree but the quality is
 * borrowed (e.g. a major IV in a context expecting minor). We still return the
 * degree so the UI can show it, but you should NOT append it to a `cp` path —
 * Hooktheory will either miss or return nonsense.
 */
export function toDegree(chordSymbol, keyTonic, mode = "major") {
  const chord = Chord.get(chordSymbol);
  if (!chord || chord.empty || !chord.tonic) return null;

  const majorTonic = relativeMajor(keyTonic, mode);
  if (!majorTonic) return null;

  const chroma = (Note.chroma(chord.tonic) - Note.chroma(majorTonic) + 12) % 12;
  const degree = SEMITONE_TO_DEGREE[chroma];
  if (!degree) return null; // chromatic root — unsupported

  const quality = (chord.quality || "").toLowerCase();
  const diatonic = quality === DIATONIC_QUALITY[degree];

  return { degree, roman: ROMAN[degree], diatonic, quality };
}

/**
 * Build the `cp` string for Hooktheory from a list of chord symbols.
 * Stops at the first chord that can't be expressed diatonically, because a
 * partial path still returns useful results but a wrong one returns garbage.
 */
export function toChildPath(chordSymbols, keyTonic, mode = "major", max = 4) {
  const degrees = [];
  for (const sym of chordSymbols.slice(-max)) {
    const d = toDegree(sym, keyTonic, mode);
    if (!d || !d.diatonic) break;
    degrees.push(d.degree);
  }
  return degrees.length ? degrees.join(",") : null;
}

/** Degree number -> concrete chord symbol in the key, e.g. 6 in C -> "Am". */
export function degreeToChordSymbol(degree, keyTonic, mode = "major") {
  const majorTonic = relativeMajor(keyTonic, mode);
  if (!majorTonic || MAJOR_SCALE_OFFSETS[degree - 1] === undefined) return null;
  const rootChroma =
    (Note.chroma(majorTonic) + MAJOR_SCALE_OFFSETS[degree - 1]) % 12;
  const name = Note.fromMidi(60 + rootChroma).replace(/\d+$/, "");
  const quality = DIATONIC_QUALITY[degree];
  const suffix =
    quality === "minor" ? "m" : quality === "diminished" ? "dim" : "";
  return `${name}${suffix}`;
}

/* ---------------------------------------------------------------------- */
/* Naming                                                                  */
/* ---------------------------------------------------------------------- */

/** "Am" -> "A minor", "Cmaj7" -> "C major seventh". Safe to hand to TTS. */
export function spokenChordName(chordSymbol) {
  const chord = Chord.get(chordSymbol);
  if (!chord || chord.empty || !chord.tonic) return chordSymbol;
  const tonic = chord.tonic
    .replace(/##/g, " double sharp")
    .replace(/bb/g, " double flat")
    .replace(/#/g, " sharp")
    .replace(/(?<=[A-G])b/g, " flat");
  const type = chord.type && chord.type !== "" ? chord.type : "major";
  return `${tonic} ${type}`;
}

/** Short display label. */
export function displayChordName(chordSymbol) {
  const chord = Chord.get(chordSymbol);
  return chord?.symbol || chordSymbol;
}

/* ---------------------------------------------------------------------- */
/* MIDI collection                                                         */
/* ---------------------------------------------------------------------- */

/**
 * Collects note-ons that land within `windowMs` of each other and reports them
 * as one chord. The window matters: a Chordcat chord button fires its notes a
 * few milliseconds apart, and without debouncing you get three "detections"
 * per chord and the speech stutters.
 *
 * Returns { handleMessage, held, reset }.
 */
export function createChordWatcher({
  onChord,
  onNotesChange,
  windowMs = 60,
  minNotes = 3,
} = {}) {
  const held = new Set();
  let timer = null;
  let lastReported = null;

  function flush() {
    timer = null;
    if (held.size < minNotes) return;

    const names = [...held]
      .sort((a, b) => a - b)
      .map((n) => Note.fromMidi(n));
    const [symbol] = Chord.detect(names, { assumePerfectFifth: true });
    if (!symbol || symbol === lastReported) return;

    lastReported = symbol;
    onChord?.({
      symbol,
      notes: [...held].sort((a, b) => a - b),
      noteNames: names,
      at: performance.now(),
    });
  }

  function handleMessage(data) {
    const status = data[0] & 0xf0;
    const note = data[1];
    const velocity = data[2];

    if (status === 0x90 && velocity > 0) {
      held.add(note);
    } else if (status === 0x80 || (status === 0x90 && velocity === 0)) {
      held.delete(note);
      if (held.size === 0) lastReported = null; // allow the same chord again
    } else {
      return;
    }

    onNotesChange?.([...held].sort((a, b) => a - b));
    clearTimeout(timer);
    timer = setTimeout(flush, windowMs);
  }

  function reset() {
    held.clear();
    lastReported = null;
    clearTimeout(timer);
    timer = null;
  }

  return { handleMessage, held, reset };
}
