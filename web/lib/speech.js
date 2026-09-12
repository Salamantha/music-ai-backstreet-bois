/**
 * speech.js — the Chordcat's missing voice.
 *
 * Wraps the Web Speech API with the two behaviours that matter for a live
 * instrument: barge-in (a new chord cancels the old announcement instead of
 * queueing behind it) and verbosity levels (terse while playing, verbose on
 * demand).
 *
 * IMPORTANT: browsers block speech until the page has had a user gesture.
 * Call unlockSpeech() inside your Start button's click handler.
 */

let unlocked = false;
let lastTerse = null;
let settings = { rate: 1.4, pitch: 1.0, volume: 0.9, voice: null };

/** Call once from a click/keydown handler, or nothing will ever be spoken. */
export function unlockSpeech() {
  if (unlocked || typeof window === "undefined") return;
  const u = new SpeechSynthesisUtterance("Chordcat voice ready");
  u.rate = settings.rate;
  u.volume = settings.volume;
  window.speechSynthesis.speak(u);
  unlocked = true;
}

export function setSpeechSettings(next) {
  settings = { ...settings, ...next };
}

export function getSpeechSettings() {
  return { ...settings };
}

/** Available system voices. Populates asynchronously in Chrome. */
export function listVoices() {
  if (typeof window === "undefined") return [];
  return window.speechSynthesis.getVoices();
}

export function onVoicesReady(cb) {
  if (typeof window === "undefined") return () => {};
  const handler = () => cb(window.speechSynthesis.getVoices());
  window.speechSynthesis.addEventListener("voiceschanged", handler);
  handler();
  return () =>
    window.speechSynthesis.removeEventListener("voiceschanged", handler);
}

function utter(text) {
  const u = new SpeechSynthesisUtterance(text);
  u.rate = settings.rate;
  u.pitch = settings.pitch;
  u.volume = settings.volume;
  if (settings.voice) u.voice = settings.voice;
  return u;
}

/**
 * Real-time announcement. Cancels whatever is currently speaking.
 * Use for chord names while the player is playing — without the cancel,
 * utterances queue and the speech falls seconds behind the music.
 *
 * Repeated identical text is suppressed so holding a chord doesn't stutter.
 */
export function speakNow(text) {
  if (!text || typeof window === "undefined") return;
  if (text === lastTerse) return;
  lastTerse = text;
  window.speechSynthesis.cancel();
  window.speechSynthesis.speak(utter(text));
}

/**
 * Queued announcement. Use for suggestions, song matches and confirmations —
 * anything the user explicitly asked for and wants to hear in full.
 */
export function speakQueued(text) {
  if (!text || typeof window === "undefined") return;
  window.speechSynthesis.speak(utter(text));
}

export function stopSpeaking() {
  if (typeof window === "undefined") return;
  window.speechSynthesis.cancel();
  lastTerse = null;
}

/** Lets the next speakNow() repeat a chord even if it matches the last one. */
export function resetTerseMemo() {
  lastTerse = null;
}

/* ---------------------------------------------------------------------- */
/* Phrase builders                                                         */
/* ---------------------------------------------------------------------- */

/**
 * "Seventy-one percent of songs go to G next."
 * nodes: [{ chordName, probability }, ...] already converted to real chords.
 */
export function phraseSuggestion(nodes, { count = 2 } = {}) {
  if (!nodes || nodes.length === 0) return "No suggestion available.";
  const top = nodes.slice(0, count);
  const parts = top.map(
    (n) => `${Math.round(n.probability * 100)} percent go to ${n.spoken}`
  );
  return `${parts.join(". ")}.`;
}

/** "That's the Let It Be progression. Also used in Don't Stop Believin'." */
export function phraseSongMatch(songs, { count = 2 } = {}) {
  if (!songs || songs.length === 0) {
    return "No songs in the database use that progression yet. That's a good sign.";
  }
  const top = songs.slice(0, count);
  const first = `That progression is used in ${top[0].song} by ${top[0].artist}`;
  if (top.length === 1) return `${first}.`;
  const rest = top
    .slice(1)
    .map((s) => `${s.song} by ${s.artist}`)
    .join(", and ");
  return `${first}. Also ${rest}.`;
}

export function phraseKey(tonic, mode) {
  return `Key of ${spellNote(tonic)} ${mode}.`;
}

/** Spells accidentals so TTS doesn't read "C#" as "C hash" or "C pound". */
export function spellNote(note) {
  if (!note) return "";
  return note
    .replace(/##/g, " double sharp")
    .replace(/bb/g, " double flat")
    .replace(/#/g, " sharp")
    .replace(/(?<=[A-G])b/g, " flat");
}
