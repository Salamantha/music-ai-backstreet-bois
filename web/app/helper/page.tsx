"use client";

/**
 * The teaching path: a conversation about what you just played.
 *
 * A deliberately separate route from the matching app. This component shares
 * none of that UI and testing it on hardware never disturbs that screen.
 *
 * It works with any MIDI device. The ChordCat is preferred by name because it
 * interleaves eight sequencer tracks and needs a harmony channel picked out,
 * but a plain keyboard sends on one channel and falls through the same path.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import {
  helperDemo, helperOverride, helperTurn, type HelperTurn,
} from "@/lib/api";
import {
  MidiCapture, channelStats, checkSupport, looksLikeChordcat,
  suggestHarmonyChannels, type MidiEvent, type MidiPort,
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
  const [ports, setPorts] = useState<MidiPort[]>([]);
  const [portId, setPortId] = useState("");
  const [noteCount, setNoteCount] = useState(0);

  const [turns, setTurns] = useState<HelperTurn[]>([]);
  const [sessionId, setSessionId] = useState("");
  const [tags, setTags] = useState<string[]>([]);
  const [said, setSaid] = useState("");
  const [shown, setShown] = useState<Record<number, boolean>>({});
  const [lastTake, setLastTake] = useState<{ events: MidiEvent[]; elapsed: number } | null>(null);

  const liveRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    const capture = new MidiCapture();
    captureRef.current = capture;
    return () => capture.disconnect();
  }, []);

  const connect = useCallback(async () => {
    setError("");
    const capture = captureRef.current!;
    const support = checkSupport();
    if (!support.supported) throw new Error(support.reason);

    const found = await capture.connect();
    if (found.length === 0) {
      throw new Error("No MIDI inputs found. Is the device plugged in and switched on?");
    }
    setPorts(found);

    // A ChordCat by name, else whatever is already sending notes, else the
    // first one. A wrong guess is recoverable from the picker; no input is not.
    const wanted =
      found.find((p) => p.id === portId) ??
      found.find(looksLikeChordcat) ??
      found.find((p) => p.messages > 0) ??
      found[0];
    await capture.select(wanted.id);
    setPortId(wanted.id);
    return capture;
  }, [portId]);

  const listen = useCallback(async () => {
    try {
      setPhase("connecting");
      const capture = await connect();
      capture.subscribe((_e, all) => setNoteCount(all.length));
      capture.start();
      setNoteCount(0);
      setPhase("listening");
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setPhase("idle");
    }
  }, [connect]);

  const ask = useCallback(
    async (events: MidiEvent[], elapsed: number) => {
      if (events.length === 0) {
        setError("Nothing came through. Check the device is playing into this port.");
        setPhase("idle");
        return;
      }
      setLastTake({ events, elapsed });
      setPhase("thinking");
      setError("");
      try {
        // Pick the track carrying harmony before analysing: a ChordCat sends
        // all eight sequencer tracks at once, a keyboard sends only one.
        const harmony = [...suggestHarmonyChannels(channelStats(events))][0] ?? null;
        const turn = await helperTurn({
          events,
          elapsed_ms: elapsed,
          session_id: sessionId || undefined,
          harmony_channel: harmony,
          intent_tags: tags,
          user_text: said.trim() || null,
        });
        setSessionId(turn.session_id);
        setTurns((prev) => [...prev, turn]);
        setSaid("");
        setPhase("answered");
      } catch (e) {
        setError(e instanceof Error ? e.message : String(e));
        setPhase("idle");
      }
    },
    [sessionId, tags, said],
  );

  const stopAndAsk = useCallback(() => {
    const capture = captureRef.current!;
    void ask(capture.snapshot(), capture.elapsed());
  }, [ask]);

  /** Run the bundled recording, for when no device is to hand. */
  const useRecorded = useCallback(async () => {
    setPhase("thinking");
    try {
      const take = await helperDemo();
      await ask(take.events, take.elapsed_ms);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setPhase("idle");
    }
  }, [ask]);

  function saveTake() {
    if (!lastTake) return;
    const stats = channelStats(lastTake.events);
    const body = {
      note: "Captured from the helper page.",
      device: ports.find((p) => p.id === portId)?.name ?? "unknown",
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
    a.download = `take-${new Date().toISOString().slice(0, 19)}.json`;
    a.click();
    URL.revokeObjectURL(url);
  }

  const busy = phase === "connecting" || phase === "thinking";
  const label = {
    idle: turns.length ? "Play me something else" : "Listen to me play",
    connecting: "Connecting…",
    listening: "Stop and ask",
    thinking: "Thinking…",
    answered: "Play me something else",
  }[phase];

  return (
    <main className="helper">
      <h1>What should I try next?</h1>
      <p className="lede">
        Play something, then stop. It will not write music for you &mdash; it can
        hear everything you play, and it has no hands.
      </p>

      <div className="panel">
        <button
          className={phase === "listening" ? "ask danger" : "ask primary"}
          onClick={() => (phase === "listening" ? stopAndAsk() : void listen())}
          disabled={busy}
        >
          {label}
        </button>

        <div className="row spread" style={{ marginTop: "0.8rem" }}>
          <span className={portId ? "signal on" : "signal off"}>
            <span className="signal-dot" />
            {phase === "listening"
              ? `listening — ${noteCount} notes`
              : portId
                ? "connected"
                : "not connected"}
          </span>
          {ports.length > 1 && (
            <label className="sub" style={{ margin: 0 }}>
              <span className="visually-hidden">MIDI input</span>
              <select
                value={portId}
                onChange={(e) => {
                  setPortId(e.target.value);
                  void captureRef.current?.select(e.target.value);
                }}
              >
                {ports.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name}
                    {p.messages > 0 ? " ·" : ""}
                  </option>
                ))}
              </select>
            </label>
          )}
        </div>

        {error && <p className="error" style={{ marginBottom: 0 }}>{error}</p>}

        {phase !== "listening" && (
          <p className="sub" style={{ marginBottom: 0, marginTop: "0.8rem" }}>
            No device to hand?{" "}
            <button className="quiet" onClick={() => void useRecorded()} disabled={busy}>
              use a recorded take
            </button>
          </p>
        )}
      </div>

      <div className="panel">
        <h2>Tell it what you want</h2>
        <textarea
          className="say"
          rows={2}
          value={said}
          onChange={(e) => setSaid(e.target.value)}
          placeholder="I want this heavier — or leave it blank."
        />
        <div className="row" style={{ marginTop: "0.6rem" }}>
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

      <div ref={liveRef} role="status" aria-live="polite" className="visually-hidden">
        {phase === "thinking" ? "Thinking" : turns.length ? "New suggestion ready" : ""}
      </div>

      {turns.map((turn, i) => (
        <div className="panel turn" key={`${turn.session_id}-${turn.turn_number}`}>
          <div className="row" style={{ marginBottom: "0.6rem" }}>
            <span className="pill">turn {turn.turn_number}</span>
            {turn.key && <span className="pill">{turn.key}</span>}
            <span className="pill">{turn.chords.length} chords</span>
            {turn.templated && <span className="pill bad">no model</span>}
          </div>

          {turn.changes.length > 0 && (
            <p className="changed">
              Since your last take:{" "}
              {turn.changes.map((c) => c.kind.replace("change.", "")).join(", ")}.
            </p>
          )}

          {turn.text.split("\n\n").map((para, n) => (
            <p key={n}>{para}</p>
          ))}

          {turn.draft && (
            <p className="draft-warning">
              Placeholder wording &mdash; the tutor has not written this node yet.
            </p>
          )}

          <div className="row" style={{ marginTop: "0.8rem" }}>
            {!shown[i] && (
              <button
                onClick={() => {
                  setShown((p) => ({ ...p, [i]: true }));
                  void helperOverride(turn.session_id, turn.node_id);
                }}
              >
                Just show me
              </button>
            )}
            {i === turns.length - 1 && lastTake && (
              <button className="quiet" onClick={saveTake}>
                Save this take as a fixture
              </button>
            )}
          </div>

          {shown[i] && (
            <p className="shown">
              You played <span className="mono">{turn.chords.slice(0, 8).join(" ")}</span>
              {turn.key ? ` in ${turn.key}` : ""}. Try {turn.plain_name} on one of them
              &mdash; not all of them. The effect comes from contrast.
            </p>
          )}

          <details>
            <summary style={{ cursor: "pointer", color: "var(--muted)" }}>
              Why is it telling me this?
            </summary>
            <p className="sub" style={{ margin: "0.6rem 0" }}>
              <span className="mono">{turn.node_id}</span> is {turn.distance} step
              {turn.distance === 1 ? "" : "s"} from{" "}
              <span className="mono">{turn.why.join(", ") || "what you played"}</span>.
              {!turn.measured && " No reading backs this one, so the absence is unobserved."}
              {turn.tied_with.length > 0 &&
                ` Scored level with: ${turn.tied_with.join(", ")}.`}
            </p>
            <div className="table-scroll">
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
            </div>
          </details>
        </div>
      ))}
    </main>
  );
}
