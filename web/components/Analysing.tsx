"use client";

import { useEffect, useState } from "react";
import PianoCat from "./PianoCat";

/** What the pipeline is actually doing, in the order it does it. */
const BEATS = [
  "Listening to your chords…",
  "Working out what key you are in…",
  "Looking for songs built on the same chords…",
  "Finding the people who play like you…",
];

/**
 * A blocking curtain over the results while the analysis runs.
 *
 * The work takes several seconds and changes the whole page underneath, so
 * leaving the old results on screen would show numbers that are about to stop
 * being true. Covering them is more honest than letting them sit there.
 */
export default function Analysing({ show }: { show: boolean }) {
  const [beat, setBeat] = useState(0);

  useEffect(() => {
    if (!show) {
      setBeat(0);
      return;
    }
    const id = setInterval(() => {
      // Hold on the last line rather than looping: cycling back to "Listening"
      // after ten seconds would read as though it had started over.
      setBeat((b) => Math.min(b + 1, BEATS.length - 1));
    }, 2600);
    return () => clearInterval(id);
  }, [show]);

  if (!show) return null;

  return (
    <div className="curtain" role="status" aria-live="polite">
      <div className="curtain-card">
        <PianoCat size={230} playing />
        <p className="curtain-beat">{BEATS[beat]}</p>
        <div className="curtain-bar" aria-hidden="true">
          <span />
        </div>
      </div>
    </div>
  );
}
