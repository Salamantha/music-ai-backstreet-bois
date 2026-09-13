"use client";

import { useEffect, useRef, useState } from "react";
import GenreFilter from "@/components/GenreFilter";
import MidiConnect from "@/components/MidiConnect";
import VoiceSing from "@/components/VoiceSing";
import ChordTimeline from "@/components/ChordTimeline";
import KeyPanel from "@/components/KeyPanel";
import Stepper, { type StepDef } from "@/components/Stepper";
import PianoCat from "@/components/PianoCat";
import Analysing from "@/components/Analysing";
import {
  SHOW_CHORD_PROGRESSION, SHOW_KEY, SHOW_WORTH_KNOWING,
} from "@/lib/features";
import { BAND, CatFace } from "@/components/CatBand";
import { JoinRoom } from "@/components/JoinRoom";
import { MatchList, SongMatches, TasteProfile } from "@/components/Results";
import {
  analyzeChords, health, joinRoom, selectableGenres,
  type AnalyzeResponse, type ChordStep, type JoinRoomResponse, type Tonality,
} from "@/lib/api";
import { loadMember, memberId } from "@/lib/room";

type InputMode = "midi" | "voice";

export default function Page() {
  const [inputMode, setInputMode] = useState<InputMode>("midi");
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
  const [room, setRoom] = useState<JoinRoomResponse | null>(null);
  const roomEnabled = backend?.room === true;

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
      label: inputMode === "voice" ? "Enable microphone" : "Plug in",
      hint: inputMode === "voice"
        ? "Let the browser hear you"
        : "Choose your MIDI input",
      complete: connected || lastChords !== null,
      reachable: true,
    },
    {
      id: "play",
      label: "Play",
      hint: "Capture a chord progression",
      complete: result !== null,
      reachable: connected || lastChords !== null,
    },
    {
      id: "results",
      label: "Results",
      hint: "Your key, songs and taste",
      complete: result !== null,
      reachable: result !== null,
    },
    {
      id: "connect",
      label: "Connect",
      hint: "Match with musicians",
      complete: room !== null,
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
      await refreshRoom(res);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  /** Once joined, every re-analysis updates the stored profile and the matches. */
  async function refreshRoom(res: AnalyzeResponse) {
    const member = loadMember();
    if (!room || !member || !res.profile) return;
    try {
      setRoom(await joinRoom({
        client_id: memberId(member),
        ...member,
        signature_progression: res.cp,
        mode: res.key?.mode ?? "major",
        profile: res.profile,
      }));
    } catch {
      // keep the previous matches; the join form is not shown again
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
    setRoom(null);
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
    "Your results",
    "Connect with musicians",
  ][step];

  return (
    <main id="main" aria-busy={busy}>
      <Analysing show={busy} />
      <header className="row spread" style={{ alignItems: "flex-start" }}>
        <div className="row" style={{ gap: "0.9rem", flexWrap: "nowrap" }}>
          <span className="logo" aria-hidden="true">
            <CatFace cat={BAND[1]} size={54} decorative />
          </span>
          <div>
          <h1>ChordLink</h1>
          <p className="lede">
            Play some chords. Find musicians who hear music the same way you
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
        {!busy && result ? "Results ready" : ""}
      </div>

      {error && (
        <div className="panel">
          <p className="error" style={{ margin: 0 }}>{error}</p>
        </div>
      )}

      {step === 0 && (
        <div className="row" style={{ marginBottom: "0.75rem", gap: 4 }}>
          {(["midi", "voice"] as InputMode[]).map((mode) => (
            <button
              key={mode}
              onClick={() => setInputMode(mode)}
              aria-pressed={inputMode === mode}
              style={{
                fontSize: 13, padding: "6px 13px",
                fontWeight: inputMode === mode ? 700 : 500,
                borderColor: inputMode === mode ? "var(--accent)" : undefined,
                color: inputMode === mode ? "var(--accent)" : undefined,
              }}
            >
              {mode === "midi" ? "MIDI controller" : "Sing / hum"}
            </button>
          ))}
        </div>
      )}

      {/* Mounted once each, at a fixed position, so stepping does not tear
          down a connection or discard captured chords. Only the panel for the
          chosen input mode is shown; the other renders show="none". */}
      <MidiConnect
        show={inputMode !== "midi" ? "none" : step === 0 ? "connect" : step === 1 ? "capture" : "none"}
        // Unlocks the next step without navigating to it. Granting MIDI access
        // is not the same as being ready to play: the right port may not be the
        // one auto-selected, and the traffic indicator is on this step.
        onConnected={() => setConnected(true)}
        onChords={onChords}
        onReset={reset}
        busy={busy}
        resetToken={resetToken}
        next={
          step === 0 ? (
            <button
              className="primary"
              onClick={() => setStep(1)}
              disabled={!steps[1].reachable}
            >
              Next: play your chords
            </button>
          ) : null
        }
      >
        {step === 1 && (
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
        )}
      </MidiConnect>
      <VoiceSing
        show={inputMode !== "voice" ? "none" : step === 0 ? "connect" : step === 1 ? "capture" : "none"}
        onConnected={() => setConnected(true)}
        onChords={onChords}
        onReset={reset}
        busy={busy}
        resetToken={resetToken}
        next={
          step === 0 ? (
            <button
              className="primary"
              onClick={() => setStep(1)}
              disabled={!steps[1].reachable}
            >
              Next: sing a melody
            </button>
          ) : null
        }
      >
        {step === 1 && (
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
        )}
      </VoiceSing>

      {step === 0 && (
        <div className="panel">
          <h2>How it works</h2>
          <p className="how">
            We learn how your music sounds, find songs with similar vibes as
            yours, and match you with like-minded musicians who are ready to jam!
          </p>
        </div>
      )}

      {step === 1 && (
        <>
          <div className="step-nav">
            <button onClick={() => setStep(0)}>Back</button>
            <span />
          </div>
        </>
      )}

      {step === 2 && result && (
        <>
          {SHOW_CHORD_PROGRESSION && (
            <ChordTimeline
              result={result}
              next={
                <button className="primary" onClick={() => setStep(3)}>
                  Next: find musicians
                </button>
              }
            />
          )}

          {SHOW_WORTH_KNOWING && result.notes.length > 0 && (
            <div className="panel">
              <h2>Worth knowing</h2>
              <ul className="note-list">
                {result.notes.map((n) => <li key={n}>{n}</li>)}
              </ul>
            </div>
          )}
          {SHOW_KEY && result.key && (
            <KeyPanel keyInfo={result.key} onOverride={override} busy={busy} />
          )}

          <SongMatches
            result={result}
            filter={
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
                bare
                showTonality={false}
              />
            }
          />
          {result.profile && <TasteProfile profile={result.profile} />}

          <div className="step-nav">
            <button onClick={() => setStep(1)}>Back to your chords</button>
            <button className="primary" onClick={() => setStep(3)}>
              Next: find musicians
            </button>
          </div>
        </>
      )}

      {step === 3 && result && (
        <>
          {!roomEnabled ? (
            result.matches.length > 0 && <MatchList matches={result.matches} />
          ) : room === null ? (
            <JoinRoom result={result} onJoined={setRoom} />
          ) : (
            <MatchList matches={room.matches} roomSize={room.room_size} />
          )}

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
            <button onClick={() => setStep(2)}>Back to your results</button>
            <button onClick={startOver}>Start over with a new progression</button>
          </div>
        </>
      )}
    </main>
  );
}
