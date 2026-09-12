"use client";

/**
 * useChordcatVoice — the whole thing in one hook.
 *
 * const v = useChordcatVoice({ key: "C", mode: "major" });
 * <button onClick={v.start}>Start</button>
 *
 * Keyboard convention used by the demo page:
 *   S  speak the next-chord suggestion
 *   M  speak the song match
 *   H  hold to hum, release to harmonise
 *   Esc stop speaking
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { initMidi, findChordcat, listen, sendProgression, allNotesOff } from "../lib/midi.js";
import { createChordWatcher, spokenChordName, toDegree, toChildPath } from "../lib/chords.js";
import {
  unlockSpeech,
  speakNow,
  speakQueued,
  stopSpeaking,
  setSpeechSettings,
  phraseSuggestion,
  phraseSongMatch,
  phraseKey,
} from "../lib/speech.js";
import { createPitchTracker } from "../lib/pitch.js";
import { harmonizeMelody } from "../lib/harmonize.js";
import {
  nextChordNodes,
  nextDegreeProbs,
  bestSongMatch,
  prewarm,
} from "../lib/hooktheory.js";
import { degreeToChordSymbol } from "../lib/chords.js";

export function useChordcatVoice({
  key: keyTonic = "C",
  mode = "major",
  bpm = 100,
  autoAnnounce = true,
  prewarmProgressions = [
    [1, 5, 6, 4],
    [6, 4, 1, 5],
    [1, 4, 5],
    [2, 5, 1],
    [1, 6, 4, 5],
  ],
} = {}) {
  const [status, setStatus] = useState("idle");
  const [error, setError] = useState(null);
  const [deviceName, setDeviceName] = useState(null);
  const [progression, setProgression] = useState([]); // chord symbols
  const [heldNotes, setHeldNotes] = useState([]);
  const [suggestions, setSuggestions] = useState([]);
  const [songs, setSongs] = useState([]);
  const [humming, setHumming] = useState(false);
  const [humNotes, setHumNotes] = useState([]);
  const [lastHarmonisation, setLastHarmonisation] = useState(null);

  const outputRef = useRef(null);
  const detachRef = useRef(null);
  const trackerRef = useRef(null);
  const humBufferRef = useRef([]);
  const progressionRef = useRef([]);

  const keyRef = useRef({ keyTonic, mode });
  useEffect(() => {
    keyRef.current = { keyTonic, mode };
  }, [keyTonic, mode]);

  /* ---------------- degrees ---------------- */

  const degrees = useCallback(() => {
    const { keyTonic: k, mode: m } = keyRef.current;
    return progressionRef.current
      .map((sym) => toDegree(sym, k, m))
      .filter((d) => d && d.diatonic)
      .map((d) => d.degree);
  }, []);

  /* ---------------- chord handling ---------------- */

  const handleChord = useCallback(
    async ({ symbol }) => {
      const spoken = spokenChordName(symbol);
      if (autoAnnounce) speakNow(spoken);

      progressionRef.current = [...progressionRef.current, symbol].slice(-8);
      setProgression([...progressionRef.current]);

      // Fetch suggestions and matches in the background so S and M are instant.
      const { keyTonic: k, mode: m } = keyRef.current;
      const cp = toChildPath(progressionRef.current, k, m, 4);
      if (!cp) {
        setSuggestions([]);
        setSongs([]);
        return;
      }

      try {
        const nodes = await nextChordNodes(cp);
        setSuggestions(
          nodes
            .filter((n) => /^[1-7]$/.test(String(n.chord_ID)))
            .slice(0, 4)
            .map((n) => {
              const sym = degreeToChordSymbol(Number(n.chord_ID), k, m);
              return {
                degree: Number(n.chord_ID),
                roman: n.chord_HTML,
                symbol: sym,
                spoken: spokenChordName(sym),
                probability: n.probability,
              };
            })
        );
      } catch {
        setSuggestions([]);
      }

      try {
        const match = await bestSongMatch(degrees());
        setSongs(match.songs);
      } catch {
        setSongs([]);
      }
    },
    [autoAnnounce, degrees]
  );

  /* ---------------- start / stop ---------------- */

  const start = useCallback(async () => {
    setError(null);
    setStatus("connecting");
    try {
      unlockSpeech(); // must happen inside the click handler's call stack

      const { inputs, outputs } = await initMidi();
      const input = findChordcat(inputs);
      const output = findChordcat(outputs);
      if (!input) throw new Error("No MIDI input found. Is the Chordcat plugged in over USB-C?");

      outputRef.current = output;
      setDeviceName(input.name);

      const watcher = createChordWatcher({
        onChord: handleChord,
        onNotesChange: setHeldNotes,
      });
      detachRef.current = listen(input, watcher.handleMessage);

      setStatus("listening");
      speakQueued(phraseKey(keyRef.current.keyTonic, keyRef.current.mode));

      prewarm(prewarmProgressions).catch(() => {});
    } catch (e) {
      setError(e.message);
      setStatus("error");
    }
  }, [handleChord, prewarmProgressions]);

  const stop = useCallback(() => {
    detachRef.current?.();
    detachRef.current = null;
    trackerRef.current?.stop();
    trackerRef.current = null;
    if (outputRef.current) allNotesOff(outputRef.current);
    stopSpeaking();
    setStatus("idle");
  }, []);

  useEffect(() => () => stop(), [stop]);

  /* ---------------- spoken actions ---------------- */

  const announceSuggestion = useCallback(() => {
    if (!suggestions.length) {
      speakQueued("No suggestion yet. Play a chord first.");
      return;
    }
    speakQueued(phraseSuggestion(suggestions));
  }, [suggestions]);

  const announceSongMatch = useCallback(() => {
    speakQueued(phraseSongMatch(songs));
  }, [songs]);

  const announceProgression = useCallback(() => {
    if (!progressionRef.current.length) {
      speakQueued("Nothing played yet.");
      return;
    }
    speakQueued(
      `You played ${progressionRef.current.map(spokenChordName).join(", ")}.`
    );
  }, []);

  /* ---------------- hum mode ---------------- */

  const startHumming = useCallback(async () => {
    if (humming) return;
    humBufferRef.current = [];
    setHumNotes([]);
    const tracker = createPitchTracker({
      onNote: (note) => {
        humBufferRef.current.push(note);
        setHumNotes([...humBufferRef.current]);
      },
    });
    trackerRef.current = tracker;
    try {
      await tracker.start();
      setHumming(true);
      speakNow("Listening. Hum your idea.");
    } catch (e) {
      setError("Microphone access denied.");
    }
  }, [humming]);

  const stopHummingAndHarmonise = useCallback(async () => {
    if (!humming) return;
    trackerRef.current?.stop();
    trackerRef.current = null;
    setHumming(false);

    const notes = humBufferRef.current;
    if (notes.length < 2) {
      speakQueued("I didn't catch enough of that. Try humming a longer phrase.");
      return;
    }

    speakQueued("Working out the chords.");
    const { keyTonic: k, mode: m } = keyRef.current;
    const result = await harmonizeMelody(notes, {
      key: k,
      mode: m,
      bpm,
      getNextProbs: nextDegreeProbs,
    });
    setLastHarmonisation(result);

    if (!result.chords.length) {
      speakQueued("I couldn't find a fit. Try again more slowly.");
      return;
    }

    speakQueued(
      `I found ${result.chords.map((c) => spokenChordName(c.symbol)).join(", ")}. Sending to the Chordcat.`
    );

    if (outputRef.current) {
      sendProgression(
        outputRef.current,
        result.chords.map((c) => c.notes),
        { bpm, beatsPerChord: 4 }
      );
    }
    return result;
  }, [humming, bpm]);

  /* ---------------- keyboard shortcuts ---------------- */

  useEffect(() => {
    if (status !== "listening") return;
    let humKeyDown = false;

    const down = (e) => {
      if (e.repeat) return;
      const k = e.key.toLowerCase();
      if (k === "s") announceSuggestion();
      else if (k === "m") announceSongMatch();
      else if (k === "p") announceProgression();
      else if (k === "escape") stopSpeaking();
      else if (k === "h" && !humKeyDown) {
        humKeyDown = true;
        startHumming();
      }
    };
    const up = (e) => {
      if (e.key.toLowerCase() === "h" && humKeyDown) {
        humKeyDown = false;
        stopHummingAndHarmonise();
      }
    };

    window.addEventListener("keydown", down);
    window.addEventListener("keyup", up);
    return () => {
      window.removeEventListener("keydown", down);
      window.removeEventListener("keyup", up);
    };
  }, [
    status,
    announceSuggestion,
    announceSongMatch,
    announceProgression,
    startHumming,
    stopHummingAndHarmonise,
  ]);

  return {
    status,
    error,
    deviceName,
    progression,
    degrees: degrees(),
    heldNotes,
    suggestions,
    songs,
    humming,
    humNotes,
    lastHarmonisation,
    start,
    stop,
    announceSuggestion,
    announceSongMatch,
    announceProgression,
    startHumming,
    stopHummingAndHarmonise,
    setSpeechSettings,
    clearProgression: () => {
      progressionRef.current = [];
      setProgression([]);
      setSuggestions([]);
      setSongs([]);
    },
  };
}
