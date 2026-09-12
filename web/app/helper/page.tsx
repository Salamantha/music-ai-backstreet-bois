"use client";

/**
 * One button, one answer.
 *
 * A deliberately separate route from the matching app: this is the teaching
 * path, it shares none of that UI, and keeping it apart means testing the
 * helper on real hardware never touches anyone else's screen.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { helperDemo, helperTurn, type HelperTurn } from "@/lib/api";
import {
  MidiCapture, channelStats, checkSupport, looksLikeChordcat,
  suggestHarmonyChannels, type MidiEvent,
} from "@/lib/webmidi";

/** Musician's words. These mirror INTENT_TAGS on the server. */
const TAGS = [
  "heavier", "jazzier", "smoother", "simpler",
  "bigger", "moodier", "busier", "more human",
];

type Phase = "idle" | "connecting" | "listening" | "thinking" | "answered";

export default function HelperPage() {
  const captureRef = useRef<MidiCapture | null>(null);
  const [phase, setPhase] = useState<Phase>("idle");
  const [error, setError] = useState("");
  const [portName, setPortName] = useState("");
  const [noteCount, setNoteCount] = useState(0);
  const [turn, setTurn] = useState<HelperTurn | null>(null);
  const [tags, setTags] = useState<string[]>([]);
  const [asked, setAsked] = useState<string[]>([]);
  const [showFacts, setShowFacts] = useState(false);
  /** Kept so a take can be saved as a test fixture after the fact. */
  const [lastTake, setLastTake] = useState<{ events: MidiEvent[]; elapsed: number } | null>(null);

  useEffect(() => {
    const capture = new MidiCapture();
    captureRef.current = capture;
    return () => capture.disconnect();
  }, []);

  const listen = useCallback(async () => {
    setError("");
    setTurn(null);
    const capture = captureRef.current!;
    try {
      const support = checkSupport();
      if (!support.supported) throw new Error(support.reason);

      setPhase("connecting");
      const ports = await capture.connect();
      if (ports.length === 0) throw new Error("No MIDI inputs. Is the ChordCat plugged in?");

      // Prefer the ChordCat by name, then anything already sending notes, then
      // whatever is first -- a wrong guess is recoverable, no input is not.
      const port =
        ports.find(looksLikeChordcat) ??
        ports.find((p) => p.messages > 0) ??
        ports[0];
      await capture.select(port.id);
      setPortName(port.name);

      capture.subscribe((_e, all) => setNoteCount(all.length));
      capture.start();
      setNoteCount(0);
      setPhase("listening");
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setPhase("idle");
    }
  }, []);

  const ask = useCallback(async () => {
    const capture = captureRef.current!;
    const events = capture.snapshot();
    const elapsed = capture.elapsed();
    setLastTake({ events, elapsed });

    if (events.length === 0) {
      setError("Nothing came through. Check the ChordCat is playing into this port.");
      setPhase("idle");
      return;
    }

    setPhase("thinking");
    setError("");
    try {
      // The ChordCat interleaves all eight sequencer tracks on separate
      // channels, so the harmony track has to be picked out before analysis.
      const stats = channelStats(events);
      const harmony = [...suggestHarmonyChannels(stats)][0] ?? null;

      const result = await helperTurn({
        events,
        elapsed_ms: elapsed,
        harmony_channel: harmony,
        intent_tags: tags,
        suggested_nodes: asked,
      });
      setTurn(result);
      if (result.node_id) setAsked((prev) => [...prev, result.node_id!]);
      setPhase("answered");
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setPhase("idle");
    }
  }, [tags, asked]);

  /** Run the bundled recording, for when the ChordCat is not in the room. */
  const useRecorded = useCallback(async () => {
    setPhase("thinking");
    setError("");
    try {
      const take = await helperDemo();
      setLastTake({ events: take.events, elapsed: take.elapsed_ms });
      const result = await helperTurn({ ...take, intent_tags: tags, suggested_nodes: asked });
      setTurn(result);
      if (result.node_id) setAsked((prev) => [...prev, result.node_id!]);
      setPhase("answered");
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setPhase("idle");
    }
  }, [tags, asked]);

  function saveTake() {
    if (!lastTake) return;
    const stats = channelStats(lastTake.events);
    const body = {
      note: "Captured from the helper page.",
      device: "Chordcat",
      elapsed_ms: lastTake.elapsed,
      harmony_channel: [...suggestHarmonyChannels(stats)][0] ?? null,
      channel_stats: stats,
      events: lastTake.events,
    };
    const url = URL.createObjectURL(
      new Blob([JSON.stringify(body, null, 1)], { type: "application/json" }),
    );
    const a = document.createElement("a");
    a.href = url;
    a.download = `chordcat-take-${new Date().toISOString().slice(0, 19)}.json`;
    a.click();
    URL.revokeObjectURL(url);
  }

  const label = {
    idle: "Listen to me play",
    connecting: "Connecting…",
    listening: "Stop and ask",
    thinking: "Thinking…",
    answered: "Listen again",
  }[phase];

  const busy = phase === "connecting" || phase === "thinking";

  return (
    <main className="helper">
      <h1>What should I try next?</h1>
      <p className="sub">
        Play something on the ChordCat, then stop. It will not write music for
        you &mdash; it can hear everything you play, and it has no hands.
      </p>

      <div className="panel">
        <button
          className={phase === "listening" ? "ask danger" : "ask primary"}
          onClick={() => void (phase === "listening" ? ask() : listen())}
          disabled={busy}
        >
          {label}
        </button>

        {phase === "listening" && (
          <p className="sub" style={{ textAlign: "center", marginBottom: 0 }}>
            Listening on <span className="mono">{portName}</span> &mdash;{" "}
            {noteCount} notes so far
          </p>
        )}
        {error && <p className="error" style={{ marginBottom: 0 }}>{error}</p>}

        {phase !== "listening" && (
          <p className="sub" style={{ margin: "12px 0 0", textAlign: "center" }}>
            No ChordCat to hand?{" "}
            <button
              onClick={() => void useRecorded()}
              disabled={busy}
              className="quiet"
            >
              use a recorded take
            </button>
          </p>
        )}
      </div>

      <div className="panel">
        <h2>Want something in particular?</h2>
        <div className="row">
          {TAGS.map((tag) => (
            <button
              key={tag}
              className="tag"
              aria-pressed={tags.includes(tag)}
              onClick={() =>
                setTags((prev) =>
                  prev.includes(tag) ? prev.filter((t) => t !== tag) : [...prev, tag],
                )
              }
            >
              {tag}
            </button>
          ))}
        </div>
      </div>

      {turn && (
        <div className="panel turn">
          {turn.key && (
            <div className="row" style={{ marginBottom: 10 }}>
              <span className="pill">{turn.key}</span>
              <span className="pill">{turn.chords.length} chords</span>
              {turn.templated && <span className="pill">no model</span>}
            </div>
          )}

          {turn.text.split("\n\n").map((para, i) => (
            <p key={i}>{para}</p>
          ))}

          {turn.draft && (
            <p className="draft-warning">
              Placeholder wording &mdash; the tutor has not written this node yet.
            </p>
          )}

          <details open={showFacts} onToggle={(e) => setShowFacts(e.currentTarget.open)}>
            <summary style={{ cursor: "pointer", color: "var(--muted)" }}>
              Why is it telling me this?
            </summary>
            <p className="sub" style={{ margin: "10px 0" }}>
              <span className="mono">{turn.node_id}</span> is {turn.distance} step
              {turn.distance === 1 ? "" : "s"} from{" "}
              <span className="mono">{turn.why.join(", ") || "what you played"}</span>.
              {!turn.measured && " No reading backs this one, so the absence is unobserved."}
              {turn.tied_with.length > 0 &&
                ` Scored level with: ${turn.tied_with.join(", ")}.`}
            </p>
            <table className="facts">
              <tbody>
                {turn.facts.map((f) => (
                  <tr key={f.id}>
                    <td>{f.kind}</td>
                    <td className="mono">{JSON.stringify(f.value)}</td>
                    <td>n={f.n_observations}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </details>

          <div className="row" style={{ marginTop: 14 }}>
            <button onClick={saveTake}>Save this take as a test fixture</button>
          </div>
        </div>
      )}
    </main>
  );
}
