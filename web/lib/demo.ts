/**
 * Synthetic ChordCat takes, for verifying the stack without hardware attached.
 *
 * Voicings are written the way the device actually sends them -- block chords
 * with a spread bass and a few ms of finger-spread between onsets -- so the
 * segmentation path exercised here is the same one real input takes.
 */
import type { MidiEvent } from "./webmidi";

export interface Demo {
  id: string;
  label: string;
  hint: string;
  chords: number[][];
}

export const DEMOS: Demo[] = [
  {
    id: "axis",
    label: "C · G · Am · F",
    hint: "The axis progression. Thousands of matches, so the sample is arbitrary.",
    chords: [[48, 60, 64, 67], [43, 55, 59, 62], [45, 57, 60, 64], [41, 53, 57, 60]],
  },
  {
    id: "royal",
    label: "F · G · Em · Am",
    hint: "The royal road. Distinctive — expect J-pop, anime and game music.",
    chords: [[41, 65, 69, 72], [43, 67, 71, 74], [40, 64, 67, 71], [45, 57, 60, 64]],
  },
  {
    id: "doowop",
    label: "C · Am · F · G",
    hint: "The 50s progression.",
    chords: [[48, 60, 64, 67], [45, 57, 60, 64], [41, 53, 57, 60], [43, 55, 59, 62]],
  },
  {
    id: "jazz",
    label: "Dm7 · G7 · Cmaj7",
    hint: "ii–V–I with sevenths, to exercise the seventh-chord path.",
    chords: [[38, 62, 65, 69, 72], [43, 67, 71, 74, 77], [48, 60, 64, 67, 71]],
  },
  {
    id: "borrowed",
    label: "C · Ab · Bb · C",
    hint: "Borrowed ♭VI–♭VII. Rare, so matches are highly identifying.",
    chords: [[48, 60, 64, 67], [44, 56, 60, 63], [46, 58, 62, 65], [48, 60, 64, 67]],
  },
];

/** Render a demo as the MIDI event stream the browser would have captured. */
export function synthesize(demo: Demo, repeats = 2, durationMs = 620): {
  events: MidiEvent[];
  elapsed: number;
} {
  const events: MidiEvent[] = [];
  let t = 0;
  for (let r = 0; r < repeats; r++) {
    for (const chord of demo.chords) {
      chord.forEach((p, i) => events.push({ k: "on", t: t + i * 9, v: 96, p }));
      chord.forEach((p, i) =>
        events.push({ k: "off", t: t + durationMs - 25 + i * 4, p }),
      );
      t += durationMs;
    }
  }
  return { events, elapsed: t };
}
