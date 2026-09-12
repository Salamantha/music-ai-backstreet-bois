/**
 * harmonize.js — sung melody in, chord progression out.
 *
 * The logic is deliberately simple and explainable, which matters more than
 * cleverness when you have to justify it in thirty seconds:
 *
 *   1. For each bar, find the scale degree the singer spent most time on.
 *   2. Every scale degree sits in exactly three diatonic triads. Those are the
 *      candidates. (Degree 3 of the scale is in I, iii and vi, for example.)
 *   3. Rank the candidates by how likely Hooktheory's 75k-song corpus says that
 *      chord is, given the chords we've already committed to.
 *   4. Take the winner, append it to the path, move to the next bar.
 *
 * Step 3 is where the "learned from real songs" claim comes from, and it's
 * honest: these are empirical transition frequencies, not a generative model.
 *
 * If the API is down or rate-limited, FALLBACK_TRANSITIONS keeps the demo
 * alive. Don't skip this — a hackathon wifi failure should not kill your pitch.
 */

import { Note } from "tonal";
import {
  MAJOR_SCALE_OFFSETS,
  relativeMajor,
  degreeToChordSymbol,
} from "./chords.js";
import { pitchClassProfile } from "./pitch.js";

/* ---------------------------------------------------------------------- */
/* Key inference                                                           */
/* ---------------------------------------------------------------------- */

// Krumhansl-Schmuckler profiles, normalised. Good enough for a hummed phrase.
const MAJOR_PROFILE = [
  6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88,
];
const MINOR_PROFILE = [
  6.33, 2.68, 3.52, 5.38, 2.6, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17,
];

function correlate(profile, template, shift) {
  let sum = 0;
  for (let i = 0; i < 12; i++) sum += profile[(i + shift) % 12] * template[i];
  return sum;
}

/**
 * Best-guess key from a set of sung notes.
 * Prefer letting the user pick the key in the UI — they already set one on the
 * Chordcat — and use this only as the default selection.
 */
export function inferKey(notes) {
  const profile = pitchClassProfile(notes);
  const total = profile.reduce((a, b) => a + b, 0);
  if (!total) return { tonic: "C", mode: "major", confidence: 0 };

  let best = { score: -Infinity };
  for (let shift = 0; shift < 12; shift++) {
    const maj = correlate(profile, MAJOR_PROFILE, shift);
    const min = correlate(profile, MINOR_PROFILE, shift);
    if (maj > best.score) best = { score: maj, chroma: shift, mode: "major" };
    if (min > best.score) best = { score: min, chroma: shift, mode: "minor" };
  }

  return {
    tonic: Note.fromMidi(60 + best.chroma).replace(/\d+$/, ""),
    mode: best.mode,
    confidence: best.score / total,
  };
}

/* ---------------------------------------------------------------------- */
/* Candidate triads                                                        */
/* ---------------------------------------------------------------------- */

/**
 * Which diatonic triads contain a given scale degree?
 * A triad rooted on degree d covers degrees d, d+2, d+4 (wrapping at 7).
 * Inverting that: degree m appears in triads rooted at m, m-2 and m-4.
 */
export function triadsContaining(scaleDegree) {
  const zero = scaleDegree - 1;
  return [zero, (zero + 5) % 7, (zero + 3) % 7].map((d) => d + 1);
}

/** MIDI note numbers for a diatonic triad, voiced near middle C. */
export function triadNotes(degree, keyTonic, mode = "major", octave = 4) {
  const majorTonic = relativeMajor(keyTonic, mode);
  const tonicMidi = 12 * (octave + 1) + Note.chroma(majorTonic);
  const zero = degree - 1;
  return [0, 2, 4].map((step) => {
    const idx = (zero + step) % 7;
    const octaveBump = Math.floor((zero + step) / 7) * 12;
    return tonicMidi + MAJOR_SCALE_OFFSETS[idx] + octaveBump;
  });
}

/** MIDI note -> scale degree in the key, or null if chromatic. */
export function midiToScaleDegree(midi, keyTonic, mode = "major") {
  const majorTonic = relativeMajor(keyTonic, mode);
  const rel = (midi - Note.chroma(majorTonic) + 120) % 12;
  const idx = MAJOR_SCALE_OFFSETS.indexOf(rel);
  return idx === -1 ? null : idx + 1;
}

/* ---------------------------------------------------------------------- */
/* Fallback transition table                                               */
/* ---------------------------------------------------------------------- */

/**
 * Approximate next-chord probabilities keyed by the previous degree, used when
 * the Hooktheory call fails. Roughly in line with what Trends reports for
 * common major-key pop, but treat these as a safety net, not as data you'd cite.
 */
const FALLBACK_TRANSITIONS = {
  start: { 1: 0.42, 6: 0.19, 4: 0.16, 5: 0.12, 2: 0.06, 3: 0.03, 7: 0.02 },
  1: { 5: 0.28, 4: 0.26, 6: 0.19, 2: 0.11, 3: 0.07, 7: 0.05, 1: 0.04 },
  2: { 5: 0.51, 1: 0.16, 4: 0.13, 6: 0.09, 3: 0.05, 7: 0.04, 2: 0.02 },
  3: { 6: 0.38, 4: 0.24, 1: 0.14, 2: 0.1, 5: 0.08, 7: 0.04, 3: 0.02 },
  4: { 1: 0.35, 5: 0.29, 6: 0.15, 2: 0.08, 4: 0.06, 3: 0.04, 7: 0.03 },
  5: { 1: 0.46, 6: 0.24, 4: 0.12, 2: 0.07, 3: 0.05, 5: 0.04, 7: 0.02 },
  6: { 4: 0.34, 5: 0.24, 1: 0.16, 2: 0.13, 3: 0.07, 7: 0.04, 6: 0.02 },
  7: { 1: 0.48, 6: 0.18, 3: 0.14, 5: 0.1, 4: 0.06, 2: 0.03, 7: 0.01 },
};

export function fallbackProbs(lastDegree) {
  return FALLBACK_TRANSITIONS[lastDegree ?? "start"] ||
    FALLBACK_TRANSITIONS.start;
}

/* ---------------------------------------------------------------------- */
/* The harmoniser                                                          */
/* ---------------------------------------------------------------------- */

/**
 * harmonize(bars, { key, mode, getNextProbs })
 *
 * getNextProbs(cpString) should resolve to { [degree]: probability }.
 * Pass hooktheory.nextDegreeProbs — see lib/hooktheory.js. If it throws or
 * returns nothing, we fall back to the static table above.
 *
 * Returns [{ bar, degree, symbol, notes, confidence, alternatives }, ...]
 */
export async function harmonize(bars, { key, mode = "major", getNextProbs }) {
  const chosen = [];
  const path = [];

  for (const bar of bars) {
    // 1. dominant scale degree in this bar
    const weights = new Map();
    for (const n of bar.notes) {
      const deg = midiToScaleDegree(n.midi, key, mode);
      if (!deg) continue; // passing chromatic note, ignore
      weights.set(deg, (weights.get(deg) || 0) + (n.weight ?? n.durMs));
    }
    if (weights.size === 0) continue;

    const melodyDegree = [...weights.entries()].sort((a, b) => b[1] - a[1])[0][0];

    // 2. candidate triads
    const candidates = triadsContaining(melodyDegree);

    // 3. rank by transition probability
    let probs;
    try {
      probs = getNextProbs ? await getNextProbs(path.join(",")) : null;
    } catch {
      probs = null;
    }
    if (!probs || Object.keys(probs).length === 0) {
      probs = fallbackProbs(path.length ? path[path.length - 1] : null);
    }

    const ranked = candidates
      .map((degree) => ({ degree, p: probs[degree] ?? 0.001 }))
      .sort((a, b) => b.p - a.p);

    const winner = ranked[0];
    const totalP = ranked.reduce((sum, r) => sum + r.p, 0) || 1;

    chosen.push({
      bar: bar.index,
      degree: winner.degree,
      symbol: degreeToChordSymbol(winner.degree, key, mode),
      notes: triadNotes(winner.degree, key, mode),
      confidence: winner.p / totalP,
      melodyDegree,
      alternatives: ranked.slice(1).map((r) => ({
        degree: r.degree,
        symbol: degreeToChordSymbol(r.degree, key, mode),
        notes: triadNotes(r.degree, key, mode),
      })),
    });

    path.push(winner.degree);
  }

  return chosen;
}

/** Convenience: full pipeline from raw sung notes to chords. */
export async function harmonizeMelody(
  notes,
  { key = null, mode = null, bpm = 100, beatsPerBar = 4, getNextProbs } = {}
) {
  const { groupIntoBars } = await import("./pitch.js");
  const inferred = key ? { tonic: key, mode: mode || "major" } : inferKey(notes);
  const bars = groupIntoBars(notes, { bpm, beatsPerBar });
  const chords = await harmonize(bars, {
    key: inferred.tonic,
    mode: inferred.mode,
    getNextProbs,
  });
  return { key: inferred, bars, chords };
}
