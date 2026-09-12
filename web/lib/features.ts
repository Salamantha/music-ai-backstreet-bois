/**
 * Feature flags for the results step.
 *
 * Off by default. Each reads an optional NEXT_PUBLIC_ override so a flag can be
 * turned back on for a run without editing code -- set it to "1" or "true" in
 * web/.env.local. The names must be written out in full rather than looked up
 * dynamically: Next.js inlines NEXT_PUBLIC_ vars at build time by matching the
 * literal text, so process.env[someVariable] would always come back undefined.
 */
function flag(value: string | undefined, fallback: boolean): boolean {
  if (value === undefined || value === "") return fallback;
  return value === "1" || value.toLowerCase() === "true";
}

/** The major/minor readings of the captured chords. */
export const SHOW_CHORD_PROGRESSION = flag(
  process.env.NEXT_PUBLIC_SHOW_CHORD_PROGRESSION,
  true,
);

/** Caveats about the analysis -- stuck notes, no song matches, and so on. */
export const SHOW_WORTH_KNOWING = flag(
  process.env.NEXT_PUBLIC_SHOW_WORTH_KNOWING,
  false,
);

/** The detected key, with one-tap alternatives. */
export const SHOW_KEY = flag(process.env.NEXT_PUBLIC_SHOW_KEY, false);
