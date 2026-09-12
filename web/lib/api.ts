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
}

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
