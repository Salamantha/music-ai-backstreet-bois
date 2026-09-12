"use client";

import { useEffect, useRef, useState } from "react";
import GenreFilter from "@/components/GenreFilter";
import MidiConnect from "@/components/MidiConnect";
import ChordTimeline from "@/components/ChordTimeline";
import KeyPanel from "@/components/KeyPanel";
import Stepper, { type StepDef } from "@/components/Stepper";
import PianoCat from "@/components/PianoCat";
import { BAND, CatFace } from "@/components/CatBand";
import { MatchList, SongMatches, TasteProfile } from "@/components/Results";
import {
  analyzeChords, health, selectableGenres,
  type AnalyzeResponse, type ChordStep, type Tonality,
} from "@/lib/api";

export default function Page() {
  const [step, setStep] = useState(0);
  const [result, setResult] = useState<AnalyzeResponse | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [backend, setBackend] = useState<Record<string, unknown> | null>(null);
  const [connected, setConnected] = useState(false);
  const [lastChords, setLastChords] = useState<ChordStep[] | null>(null);
  const [genres, setGenres] = useState<string[]>([]);
  const [genrePalette, setGenrePalette] = useState<Record<string, number>>({});
  const [genreOptions, setGenreOptions] = useState<string[]>([]);
  const [tonality, setTonality] = useState<Tonality>("any");
  // Bumping this tells MidiConnect to throw away the take it is holding.
  const [resetToken, setResetToken] = useState(0);

  // Moving between steps changes what the page is about, so focus follows.
  // Without this a screen-reader user is left where the old content was.
  const headingRef = useRef<HTMLHeadingElement>(null);
  const firstRender = useRef(true);

  useEffect(() => {
    health().then(setBackend).catch(() => setBackend(null));
    selectableGenres().then(setGenreOptions).catch(() => setGenreOptions([]));
  }, []);

  useEffect(() => {
    if (firstRender.current) {
      firstRender.current = false;
      return;
    }
    headingRef.current?.focus();
  }, [step]);

  const steps: StepDef[] = [
    {
      id: "plug-in",
      label: "Plug in",
      hint: "Choose your MIDI input",
      complete: connected || lastChords !== null,
      reachable: true,
    },
    {
      id: "play",
      label: "Play",
      hint: "Capture a progression",
      complete: result !== null,
      reachable: connected || lastChords !== null,
    },
    {
      id: "connect",
      label: "Connect",
      hint: "Musicians who match you",
      complete: false,
      reachable: result !== null,
    },
  ];

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
      setStep(2);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  /** Back to a blank page: no take, no results, no filters, step one. */
  function startOver() {
    setResetToken((t) => t + 1);
    setGenres([]);
    setTonality("any");
    setStep(0);
    reset();
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
    if (lastChords) void onChords(lastChords, undefined, next);
  }

  function override(pc: number, mode: string) {
    if (lastChords) void onChords(lastChords, { pc, mode });
  }

  const heading = [
    "Plug in your instrument",
    "Play your chords",
    "Connect with musicians",
  ][step];

  return (
    <main id="main">
      <header className="row spread" style={{ alignItems: "flex-start" }}>
        <div className="row" style={{ gap: "0.9rem", flexWrap: "nowrap" }}>
          <span className="logo" aria-hidden="true">
            <CatFace cat={BAND[1]} size={54} decorative />
          </span>
          <div>
          <h1>ChordCat Connect</h1>
          <p className="lede">
            Play a progression. Find the musicians who hear harmony the way you
            do. Brought to you by The HackStreet Bois.
          </p>
          </div>
        </div>
        <span className={`pill ${backend ? "ok" : "bad"}`}>
          {backend
            ? `${backend.personas} musicians looking to jam`
            : "backend unreachable"}
        </span>
      </header>

      <Stepper steps={steps} current={step} onGo={setStep} />

      {/* The visible heading for the current step, and the focus target when
          the step changes. */}
      <h2 ref={headingRef} tabIndex={-1} className="visually-hidden">
        {heading}
      </h2>

      <div role="status" aria-live="polite" className="visually-hidden">
        {busy ? "Analysing your progression" : result ? "Results ready" : ""}
      </div>

      {error && (
        <div className="panel">
          <p className="error" style={{ margin: 0 }}>{error}</p>
        </div>
      )}

      {/* Mounted once, at a fixed position, so stepping does not tear down the
          MIDI connection or discard captured chords. */}
      <MidiConnect
        show={step === 0 ? "connect" : step === 1 ? "capture" : "none"}
        // Unlocks the next step without navigating to it. Granting MIDI access
        // is not the same as being ready to play: the right port may not be the
        // one auto-selected, and the traffic indicator is on this step.
        onConnected={() => setConnected(true)}
        onChords={onChords}
        onReset={reset}
        busy={busy}
        resetToken={resetToken}
      />

      {step === 0 && (
        <>
          <div className="panel">
            <h2>How it works</h2>
            <ol className="how">
              <li>
                <strong>Plug in.</strong> Connect your ChordCat — or any MIDI
                keyboard — so the browser can hear what you play.
              </li>
              <li>
                <strong>Play a few chords.</strong> Four is plenty. Anything you
                like the sound of.
              </li>
              <li>
                <strong>Meet the people who play like you.</strong> We work out
                your key and your progression, find the songs built on it, and
                rank everyone else here by how close their harmony is to yours.
              </li>
            </ol>
          </div>

          <div className="step-nav">
            <span />
            <button
              className="primary"
              onClick={() => setStep(1)}
              disabled={!steps[1].reachable}
            >
              Next: play your chords
            </button>
          </div>
        </>
      )}

      {step === 1 && (
        <>
          <details className="panel">
            <summary style={{ cursor: "pointer", fontWeight: 700 }}>
              Narrow the search (optional)
            </summary>
            <p className="sub" style={{ marginTop: "0.75rem" }}>
              Leave these alone and every match is considered.
            </p>
            <GenreFilter
              options={genreOptions}
              counts={genrePalette}
              selected={genres}
              onChange={applyGenres}
              tonality={tonality}
              onTonality={applyTonality}
              hasResults={result !== null}
              busy={busy}
              bare
            />
          </details>

          {busy && (
            <div className="panel">
              <p style={{ margin: 0 }}>Analysing — this can take a moment…</p>
            </div>
          )}

          <div className="step-nav">
            <button onClick={() => setStep(0)}>Back</button>
            <span />
          </div>
        </>
      )}

      {step === 2 && result && (
        <>
          {result.notes.length > 0 && (
            <div className="panel">
              <h2>Worth knowing</h2>
              <ul className="note-list">
                {result.notes.map((n) => <li key={n}>{n}</li>)}
              </ul>
            </div>
          )}

          <ChordTimeline result={result} />
          {result.key && (
            <KeyPanel keyInfo={result.key} onOverride={override} busy={busy} />
          )}

          <GenreFilter
            options={genreOptions}
            counts={
              Object.keys(genrePalette).length > 0
                ? genrePalette
                : result.available_genres
            }
            selected={genres}
            onChange={applyGenres}
            tonality={tonality}
            onTonality={applyTonality}
            hasResults
            busy={busy}
          />

          <SongMatches result={result} />
          {result.profile && <TasteProfile profile={result.profile} />}
          <MatchList result={result} />

          <div className="panel mascot-panel">
            <PianoCat />
            <div>
              <h2>Go and play with someone</h2>
              <p className="sub" style={{ marginBottom: 0 }}>
                Domino has done his part. The rest is up to you and whoever is
                closest to the top of that list.
              </p>
            </div>
          </div>

          <div className="step-nav">
            <button onClick={() => setStep(1)}>Back to your chords</button>
            <button onClick={startOver}>Start over with a new progression</button>
          </div>
        </>
      )}
    </main>
  );
}
