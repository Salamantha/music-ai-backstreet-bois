"use client";

import { useEffect, useState } from "react";
import GenreFilter from "@/components/GenreFilter";
import MidiConnect from "@/components/MidiConnect";
import ChordTimeline from "@/components/ChordTimeline";
import KeyPanel from "@/components/KeyPanel";
import { MatchList, SongMatches, TasteProfile } from "@/components/Results";
import {
  analyzeChords, health, selectableGenres,
  type AnalyzeResponse, type ChordStep, type Tonality,
} from "@/lib/api";

export default function Page() {
  const [result, setResult] = useState<AnalyzeResponse | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [backend, setBackend] = useState<Record<string, unknown> | null>(null);
  const [lastChords, setLastChords] = useState<ChordStep[] | null>(null);
  const [genres, setGenres] = useState<string[]>([]);
  // Genres available before filtering. Kept across a filtered re-analysis so
  // narrowing to one genre does not collapse the chooser to that single option.
  const [genrePalette, setGenrePalette] = useState<Record<string, number>>({});
  const [genreOptions, setGenreOptions] = useState<string[]>([]);
  const [tonality, setTonality] = useState<Tonality>("any");

  useEffect(() => {
    health().then(setBackend).catch(() => setBackend(null));
    selectableGenres().then(setGenreOptions).catch(() => setGenreOptions([]));
  }, []);

  async function onChords(
    chords: ChordStep[],
    key?: { pc: number; mode: string },
    wanted: string[] = genres,
    wantedTonality: Tonality = tonality,
  ) {
    setBusy(true);
    setError("");
    setLastChords(chords);
    try {
      const res = await analyzeChords(chords, {
        keyTonicPc: key?.pc,
        keyMode: key?.mode,
        genres: wanted,
        tonality: wantedTonality,
      });
      setResult(res);
      if (wanted.length === 0) setGenrePalette(res.available_genres);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  function reset() {
    setResult(null);
    setError("");
    setLastChords(null);
    setGenrePalette({});
  }

  function applyTonality(next: Tonality) {
    setTonality(next);
    if (lastChords) void onChords(lastChords, undefined, genres, next);
  }

  function applyGenres(next: string[]) {
    setGenres(next);
    // Only re-run if there is something to re-run. Chosen before a capture,
    // the selection simply applies to the next analysis.
    if (lastChords) void onChords(lastChords, undefined, next);
  }

  function override(pc: number, mode: string) {
    if (lastChords) void onChords(lastChords, { pc, mode });
  }

  return (
    <main>
      <div className="row spread">
        <div>
          <h1>ChordCat Connect</h1>
          <p className="sub">
            Play a progression on your ChordCat. Find the musicians who hear harmony the way you do.
          </p>
        </div>
        <span className={`pill ${backend ? "ok" : "bad"}`}>
          {backend
            ? `backend up · ${backend.personas} musicians`
            : "backend unreachable"}
        </span>
      </div>

      <GenreFilter
        options={genreOptions}
        counts={
          Object.keys(genrePalette).length > 0
            ? genrePalette
            : result?.available_genres ?? {}
        }
        selected={genres}
        onChange={applyGenres}
        tonality={tonality}
        onTonality={applyTonality}
        hasResults={result !== null}
        busy={busy}
      />

      <MidiConnect onChords={onChords} onReset={reset} busy={busy} />

      {busy && <div className="panel"><p style={{ margin: 0 }}>Analysing…</p></div>}
      {error && <div className="panel"><p className="error" style={{ margin: 0 }}>{error}</p></div>}

      {result && (
        <>
          {result.notes.length > 0 && (
            <div className="panel">
              <ul className="note-list">
                {result.notes.map((n) => <li key={n}>{n}</li>)}
              </ul>
            </div>
          )}
          <ChordTimeline result={result} />
          {result.key && (
            <KeyPanel keyInfo={result.key} onOverride={override} busy={busy} />
          )}
          <SongMatches result={result} />
          {result.profile && <TasteProfile profile={result.profile} />}
          <MatchList result={result} />
        </>
      )}
    </main>
  );
}
