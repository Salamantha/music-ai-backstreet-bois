import type { MidiEvent } from "./webmidi";

const BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";

export interface Chord {
  index: number; start_ms: number; end_ms: number;
  root: string; quality: string; inversion: number;
  symbol: string; roman: string | null; cp: string | null; pitches: number[];
}
export interface KeyInfo {
  tonic_pc: number; mode: string; name: string; confidence: number;
  source: string; modulation_suspected: boolean;
  alternatives: { tonic_pc: number; mode: string; name: string; confidence: number }[];
}
export interface Song {
  artist: string; song: string; section: string; url: string;
  score: number; matched_ngrams: string[];
  /** The recording on YouTube, when the source knew one. */
  video_url: string;
  genres: string[];
  song_chords: string[];
  matched_chords: string[];
  song_key: string;
  coverage: number;
  /** Every section that matched; `section` is the one the chords come from. */
  sections: string[];
}
export interface Artist { artist: string; score: number; songs: string[] }
export interface Harmonic {
  mode: string; seventh_density: number; borrowed_rate: number;
  mean_progression_rarity: number; key_spread: number; chord_variety: number;
  mean_chord_duration_s: number; cadence_profile: Record<string, number>;
}
export interface Profile {
  genres: Record<string, number>; artists: Record<string, number>;
  eras: Record<string, number>; moods: Record<string, number>;
  harmonic: Harmonic; taste_document: string;
}
export interface Match {
  id: string; name: string; instrument: string; city: string; bio: string;
  score: number; percentile: number; components: Record<string, number>;
  shared_artists: string[]; shared_genres: string[]; shared_harmonic: string[];
  rationale: string; signature_progression: string;
}
export interface AnalyzeResponse {
  session_id: string; chords: Chord[]; key: KeyInfo | null; cp: string;
  romans: string[]; unmapped: { index: number; label: string; reason: string }[];
  songs: Song[]; artists: Artist[]; profile: Profile | null; matches: Match[];
  requests_spent: number; queried: string[];
  segmentation_mode: string; stuck_notes: number; notes: string[];
  prefer_flats: boolean;
  available_genres: Record<string, number>;
  applied_genres: string[];
  applied_tonality: string;
  alternate_key_name: string;
  alternate_key_mode: string;
  alternate_romans: string[];
  alternate_cp: string;
}

export type Tonality = "any" | "major" | "minor";

export async function analyze(
  events: MidiEvent[],
  opts: { sessionEndMs?: number; keyTonicPc?: number; keyMode?: string; budget?: number } = {},
): Promise<AnalyzeResponse> {
  const res = await fetch(`${BASE}/api/analyze`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      events,
      session_end_ms: opts.sessionEndMs,
      key_tonic_pc: opts.keyTonicPc,
      key_mode: opts.keyMode,
      budget: opts.budget,
    }),
  });
  if (!res.ok) {
    const detail = await res.text();
    throw new Error(`Analysis failed (${res.status}): ${detail.slice(0, 300)}`);
  }
  return res.json();
}

export async function health(): Promise<Record<string, unknown>> {
  const res = await fetch(`${BASE}/api/health`);
  if (!res.ok) throw new Error(`Backend unreachable (${res.status})`);
  return res.json();
}

export interface Candidate {
  root: string; quality: string; symbol: string;
  inversion: number; extensions: string[]; score: number;
}
export interface Identified {
  symbol: string; root: string; quality: string; inversion: number;
  extensions: string[]; bass: string; roman: string | null; cp: string | null;
  pitch_classes: string[]; candidates: Candidate[];
}

/** Identify one held chord. Does no network I/O beyond this call -- safe to
 *  fire on every change to the set of held notes. */
export async function identify(
  pitches: number[],
  key?: { tonicPc: number; mode: string },
): Promise<Identified> {
  const res = await fetch(`${BASE}/api/identify`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      pitches,
      key_tonic_pc: key?.tonicPc,
      key_mode: key?.mode,
    }),
  });
  if (!res.ok) throw new Error(`Identify failed (${res.status})`);
  return res.json();
}

export interface ChordStep {
  pitches: number[];
  duration_ms?: number;
}

/** Analyse a progression the player already separated into chords. */
export async function analyzeChords(
  chords: ChordStep[],
  opts: {
    keyTonicPc?: number;
    keyMode?: string;
    genres?: string[];
    tonality?: Tonality;
  } = {},
): Promise<AnalyzeResponse> {
  const res = await fetch(`${BASE}/api/analyze`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      chords,
      key_tonic_pc: opts.keyTonicPc,
      key_mode: opts.keyMode,
      genres: opts.genres ?? [],
      tonality: opts.tonality ?? "any",
    }),
  });
  if (!res.ok) {
    const detail = await res.text();
    throw new Error(`Analysis failed (${res.status}): ${detail.slice(0, 300)}`);
  }
  return res.json();
}

export interface JoinRoomRequest {
  client_id: string;
  name: string;
  city: string;
  instrument: string;
  signature_progression: string;
  mode: string;
  profile: Profile;
}

export interface JoinRoomResponse {
  room_size: number;
  matches: Match[];
}

/** Store the player's profile in the room and rank them against everyone else. */
export async function joinRoom(req: JoinRoomRequest): Promise<JoinRoomResponse> {
  const res = await fetch(`${BASE}/api/room/join`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(req),
  });
  if (!res.ok) {
    const detail = await res.text();
    throw new Error(`Could not join the room (${res.status}): ${detail.slice(0, 300)}`);
  }
  return res.json();
}

/** Genres that can be chosen before an analysis runs. */
export async function selectableGenres(): Promise<string[]> {
  const res = await fetch(`${BASE}/api/genres`);
  if (!res.ok) throw new Error(`Could not load genres (${res.status})`);
  return (await res.json()).genres as string[];
}

/**
 * Reduce a roman numeral to the triad it is built on.
 *
 * Mirrors the server, which queries in plain triads so that `i ii` matches a
 * song written `i7 ii7`. The highlighting has to compare the same way, or the
 * matched chords in such a song would appear unmatched.
 */
const _ROMAN_DEGREE: Record<string, number> = {
  i: 1, ii: 2, iii: 3, iv: 4, v: 5, vi: 6, vii: 7,
};

/** Suffixes that begin with a digit, which would fuse with the degree number. */
const _SUPERSCRIPT: Record<string, string> = {
  "7": "\u2077", "6": "\u2076", "maj7": "maj\u2077",
  "\u00b07": "\u00b0\u2077", "7sus4": "\u2077sus4",
};

/**
 * A roman numeral as a plain number, Nashville style: `vi` -> `6m`,
 * `bVII` -> `b7`, `V7` -> `5⁷`, `viiø` -> `7ø`.
 *
 * Display only -- every comparison still runs on the roman form, which is what
 * both our analysis and Hooktheory's song data are written in.
 *
 * Sevenths and sixths become superscripts because `5` + `7` would otherwise
 * read as fifty-seven. Lowercase means minor, so it earns an `m` -- except
 * where the suffix already names the quality (`°`, `ø`), which would make the
 * `m` redundant.
 */
export function toNumber(roman: string | null | undefined): string {
  if (!roman) return "\u2014";
  const m = /^([b#\u266d\u266f]*)([ivxIVX]+)(.*)$/.exec(roman.trim());
  if (!m) return roman;
  const [, accidental, numeral, rawSuffix] = m;
  const degree = _ROMAN_DEGREE[numeral.toLowerCase()];
  if (!degree) return roman;

  // Applied chords name a second degree after the slash: V/vi -> 5/6m.
  const applied = rawSuffix.indexOf("/");
  if (applied !== -1) {
    const head = toNumber(`${accidental}${numeral}${rawSuffix.slice(0, applied)}`);
    return `${head}/${toNumber(rawSuffix.slice(applied + 1))}`;
  }

  const suffix = _SUPERSCRIPT[rawSuffix] ?? rawSuffix;
  const namesQuality = /^[\u00b0o0\u00f8+]/.test(rawSuffix);
  const minor = numeral === numeral.toLowerCase() && !namesQuality;
  const quality = minor ? "m" : "";

  // minmaj7 would otherwise run together as 6mmaj7.
  if (minor && rawSuffix.startsWith("maj")) {
    return `${accidental}${degree}m(${suffix})`;
  }
  return `${accidental}${degree}${quality}${suffix}`;
}

export function stripModifiers(roman: string): string {
  const m = /^([b#]*)([ivxIVX]+)(o|0|ø|\+)?/.exec(roman.trim());
  return m ? `${m[1]}${m[2]}${m[3] ?? ""}` : roman.trim();
}

/** Indices of chords covered by an occurrence of `pattern`. */
export function matchedPositions(chords: string[], pattern: string[]): Set<number> {
  const hits = new Set<number>();
  if (pattern.length === 0) return hits;
  const norm = chords.map(stripModifiers);
  const want = pattern.map(stripModifiers);
  for (let i = 0; i + want.length <= norm.length; i++) {
    if (want.every((w, j) => norm[i + j] === w)) {
      for (let j = 0; j < want.length; j++) hits.add(i + j);
      i += want.length - 1;
    }
  }
  return hits;
}

/**
 * A YouTube search for a song, rather than a specific video.
 *
 * The video id embedded in a TheoryTab is whatever its contributor linked --
 * often a cover, a lyric video, or something since taken down. A search always
 * resolves to the actual song.
 */
export function youtubeSearch(artist: string, song: string): string {
  const q = encodeURIComponent(`${artist} ${song}`.replace(/\s+/g, " ").trim());
  return `https://www.youtube.com/results?search_query=${q}`;
}

export interface HelperFact {
  id: string; kind: string; value: unknown;
  n_observations: number; confidence: number;
}

export interface HelperTurn {
  node_id: string | null;
  plain_name: string | null;
  text: string;
  why: string[];
  distance: number;
  measured: boolean;
  tied_with: string[];
  draft: boolean;
  templated: boolean;
  facts: HelperFact[];
  chords: string[];
  key: string | null;
}

export interface HelperTurnRequest {
  events: MidiEvent[];
  elapsed_ms: number;
  harmony_channel?: number | null;
  user_text?: string | null;
  intent_tags?: string[];
  suggested_nodes?: string[];
  tried_nodes?: string[];
}

/** Ask the helper what to try next. No Hooktheory I/O, so no shared quota. */
export async function helperTurn(req: HelperTurnRequest): Promise<HelperTurn> {
  const res = await fetch(`${BASE}/api/helper/turn`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(req),
  });
  if (!res.ok) throw new Error(`helper failed: ${res.status} ${await res.text()}`);
  return res.json();
}

/** The bundled ChordCat recording, for testing with no hardware present. */
export async function helperDemo(): Promise<HelperTurnRequest & { elapsed_ms: number }> {
  const res = await fetch(`${BASE}/api/helper/demo`);
  if (!res.ok) throw new Error(`no recorded take available (${res.status})`);
  return res.json();
}
