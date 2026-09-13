export interface VoiceSuggestion {
  degree: number;
  roman: string;
  symbol: string;
  spoken: string;
  probability: number;
}

export interface VoiceSongMatch {
  artist: string;
  song: string;
  section: string;
  url: string;
}

export interface HumNote {
  midi: number;
  startMs: number;
  durMs: number;
  cents: number;
}

export interface HarmonisedChord {
  degree: number;
  symbol: string;
  notes: number[];
}

export interface Harmonisation {
  key: { tonic: string; mode: string };
  bars: unknown[];
  chords: HarmonisedChord[];
}

export interface ChordcatVoice {
  status: "idle" | "connecting" | "listening" | "error";
  error: string | null;
  deviceName: string | null;
  progression: string[];
  degrees: number[];
  heldNotes: number[];
  suggestions: VoiceSuggestion[];
  songs: VoiceSongMatch[];
  humming: boolean;
  humNotes: HumNote[];
  lastHarmonisation: Harmonisation | null;
  start: () => Promise<void>;
  stop: () => void;
  announceSuggestion: () => void;
  announceSongMatch: () => void;
  announceProgression: () => void;
  startHumming: () => Promise<void>;
  stopHummingAndHarmonise: () => Promise<Harmonisation | undefined>;
  setSpeechSettings: (settings: Record<string, unknown>) => void;
  clearProgression: () => void;
}

export interface ChordcatVoiceOptions {
  key?: string;
  mode?: string;
  bpm?: number;
  autoAnnounce?: boolean;
  prewarmProgressions?: number[][];
}

export function useChordcatVoice(options?: ChordcatVoiceOptions): ChordcatVoice;
