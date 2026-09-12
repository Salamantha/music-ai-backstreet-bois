/**
 * midi.js — Web MIDI in and out.
 *
 * Web MIDI requires a secure context: https:// or http://localhost.
 * A Vercel preview URL is fine; a plain http:// LAN address is not.
 * Chrome and Edge support it. Safari and Firefox do not — use Chrome tomorrow.
 */

let access = null;

export async function initMidi() {
  if (typeof navigator === "undefined" || !navigator.requestMIDIAccess) {
    throw new Error(
      "Web MIDI unavailable. Use Chrome over https:// or localhost."
    );
  }
  access = await navigator.requestMIDIAccess({ sysex: false });
  return {
    inputs: [...access.inputs.values()],
    outputs: [...access.outputs.values()],
    onStateChange(cb) {
      access.onstatechange = cb;
    },
  };
}

/** Chordcat enumerates its port name differently per OS, so match loosely. */
export function findChordcat(ports) {
  const hit = ports.find((p) => /chordcat|toraiz/i.test(p.name || ""));
  return hit || ports[0] || null;
}

/**
 * Attach a raw message listener. Returns a detach function.
 * handler receives the Uint8Array data.
 */
export function listen(input, handler) {
  const wrapped = (e) => handler(e.data);
  input.onmidimessage = wrapped;
  return () => {
    if (input.onmidimessage === wrapped) input.onmidimessage = null;
  };
}

/* ---------------------------------------------------------------------- */
/* Output                                                                  */
/* ---------------------------------------------------------------------- */

const NOTE_ON = 0x90;
const NOTE_OFF = 0x80;

/**
 * Play a chord on the Chordcat.
 *
 * Requires Chordcat firmware v1.30 or later for the device to record incoming
 * MIDI in real time. Check Settings before you rely on this — earlier firmware
 * will pass the notes through but will not capture them into a pattern.
 */
export function sendChord(
  output,
  midiNotes,
  { channel = 0, velocity = 100, durationMs = 700, atTime = null } = {}
) {
  if (!output || !midiNotes?.length) return;
  const t = atTime ?? performance.now();
  for (const n of midiNotes) {
    output.send([NOTE_ON | channel, n, velocity], t);
    output.send([NOTE_OFF | channel, n, 0], t + durationMs);
  }
}

/** Play a progression back-to-back. chords is an array of MIDI note arrays. */
export function sendProgression(
  output,
  chords,
  { channel = 0, velocity = 100, bpm = 100, beatsPerChord = 4 } = {}
) {
  const msPerChord = (60000 / bpm) * beatsPerChord;
  const start = performance.now() + 120; // small lead-in so nothing is clipped
  chords.forEach((notes, i) => {
    sendChord(output, notes, {
      channel,
      velocity,
      durationMs: msPerChord * 0.9,
      atTime: start + i * msPerChord,
    });
  });
  return msPerChord * chords.length;
}

/** Emergency stop — kills anything hanging if a note-off got lost. */
export function allNotesOff(output, channel = 0) {
  if (!output) return;
  output.send([0xb0 | channel, 123, 0]);
}
