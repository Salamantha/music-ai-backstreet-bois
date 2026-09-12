"use client";

import { toNumber, type AnalyzeResponse } from "@/lib/api";

/** The modes whose tonic triad is major. Everything else reads as minor. */
const MAJOR_MODES = new Set(["major", "lydian", "mixolydian"]);

/**
 * Just the note a reading is built on: "F mixolydian" -> "F".
 *
 * The mode name is the one piece of this that needs a theory background to
 * read, and the section title already says whether it is heard as major or
 * minor -- so dropping the word loses nothing and invents nothing. Calling
 * F mixolydian "F major" would have been the lie.
 */
function tonicOf(keyName: string): string {
  return keyName.split(" ")[0] || keyName;
}

interface Reading {
  /** "F mixolydian", "G minor". */
  keyName: string;
  mode: string;
  romans: (string | null)[];
}

interface Hole {
  index: number;
  label: string;
  reason: string;
}

/**
 * One way of hearing the progression, as its own block of chord cards.
 *
 * The two readings share a pitch-class set, so neither is more correct than
 * the other from the notes alone -- which is why they get equal billing
 * rather than one being stacked underneath the other as a second row.
 */
function ReadingBlock({
  reading, symbols, holes,
}: {
  reading: Reading;
  symbols: string[];
  holes: Map<number, Hole>;
}) {
  return (
    <>
      <p className="sub" style={{ margin: "0 0 10px" }}>
        Built around <strong>{tonicOf(reading.keyName)}</strong>.
      </p>

      <div className="chords">
        {symbols.map((symbol, i) => {
          const hole = holes.get(i);
          return (
            <div key={i} className={`chord${hole ? " hole" : ""}`}>
              <div className="sym">{symbol}</div>
              <div className="rom">{toNumber(reading.romans[i])}</div>
            </div>
          );
        })}
      </div>
    </>
  );
}

export default function ChordTimeline({ result }: { result: AnalyzeResponse }) {
  const holes = new Map(result.unmapped.map((u) => [u.index, u]));
  const symbols = result.chords.map((c) => c.symbol);

  const primary: Reading = {
    keyName: result.key?.name ?? "an unknown key",
    mode: result.key?.mode ?? "major",
    romans: result.chords.map((c) => c.roman),
  };

  const alternate: Reading | null = result.alternate_key_name
    ? {
        keyName: result.alternate_key_name,
        mode: result.alternate_key_mode,
        romans: result.alternate_romans,
      }
    : null;

  // With only one reading there is nothing to separate, so show it plainly.
  if (!alternate) {
    return (
      <div className="panel">
        <h2 style={{ marginTop: 0 }}>Chord progression</h2>
        <ReadingBlock reading={primary} symbols={symbols} holes={holes} />
        <Caveats result={result} />
      </div>
    );
  }

  // Ask each reading what it is rather than assuming the alternate is always
  // the opposite family -- the backend decides that, and this should follow it.
  const major = MAJOR_MODES.has(primary.mode) ? primary : alternate;
  const minor = major === primary ? alternate : primary;

  const tonality = result.applied_tonality;
  // With no stated preference both readings are equally live, so both open.
  // With a preference the other one is still worth keeping -- a player often
  // thinks in the reading we did not pick -- but it folds away.
  const sections: { title: string; reading: Reading; open: boolean }[] = [
    { title: "As a major progression", reading: major, open: tonality !== "minor" },
    { title: "As a minor progression", reading: minor, open: tonality === "minor" },
  ];
  // The reading you asked for leads. Without a preference the major one does,
  // which is only a tie-break -- neither is more correct than the other.
  if (tonality === "minor") sections.reverse();

  return (
    <div className="panel">
      <h2 style={{ marginTop: 0 }}>Chord progression</h2>

      {sections.map((s) => (
        <details key={s.title} className="reading" open={s.open}>
          <summary>
            <span className="reading-title">{s.title}</span>{" "}
            <span className="meta">{tonicOf(s.reading.keyName)}</span>
          </summary>
          <div className="reading-body">
            <ReadingBlock reading={s.reading} symbols={symbols} holes={holes} />
          </div>
        </details>
      ))}

      <Caveats result={result} />
    </div>
  );
}

function Caveats({ result }: { result: AnalyzeResponse }) {
  if (result.unmapped.length === 0) return null;
  return (
    <p className="sub" style={{ margin: "12px 0 0" }}>
      We could not look up {result.unmapped.length} of your chords, so we
      searched the rest in pieces rather than all in one go.
    </p>
  );
}
