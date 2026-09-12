/**
 * hooktheory.js — browser client for your own proxy, never for Hooktheory direct.
 *
 * Never call api.hooktheory.com from the browser: your credentials would be in
 * the bundle and CORS will fight you. Everything goes through server/hooktheory_proxy.py.
 *
 * The in-memory cache here is the second line of defence. The proxy caches too,
 * but this one saves you the round trip entirely, which matters when the
 * harmoniser asks for probabilities once per bar.
 */

const BASE = process.env.NEXT_PUBLIC_HOOKTHEORY_PROXY || "http://localhost:8000";

const nodeCache = new Map();
const songCache = new Map();

async function get(path, params) {
  const url = new URL(path, BASE);
  Object.entries(params).forEach(([k, v]) => {
    if (v !== null && v !== undefined && v !== "") url.searchParams.set(k, v);
  });
  const res = await fetch(url.toString());
  if (!res.ok) throw new Error(`Hooktheory proxy ${res.status}`);
  return res.json();
}

/**
 * Raw next-chord nodes for a child path.
 * cp is a comma-separated degree list, e.g. "1,5,6" — or "" for overall stats.
 * Returns [{ chord_ID, chord_HTML, probability, child_path }, ...]
 */
export async function nextChordNodes(cp = "") {
  if (nodeCache.has(cp)) return nodeCache.get(cp);
  const data = await get("/api/nodes", { cp });
  nodeCache.set(cp, data);
  return data;
}

/**
 * Same data reshaped for the harmoniser: { [degree]: probability }.
 * Non-triad entries (sevenths, inversions, applied chords) are dropped, because
 * we only ever suggest diatonic triads.
 */
export async function nextDegreeProbs(cp = "") {
  const nodes = await nextChordNodes(cp);
  const out = {};
  for (const n of nodes) {
    const id = String(n.chord_ID);
    if (!/^[1-7]$/.test(id)) continue; // skip 4/1, 57, etc.
    out[Number(id)] = n.probability;
  }
  return out;
}

/**
 * Songs whose progression contains this child path.
 * Returns [{ artist, song, section, url }, ...]
 */
export async function songsFor(cp) {
  if (!cp) return [];
  if (songCache.has(cp)) return songCache.get(cp);
  const data = await get("/api/songs", { cp });
  songCache.set(cp, data);
  return data;
}

/**
 * Longest-match lookup: try the full progression, then drop the oldest chord
 * until something comes back. A four-chord loop often has no exact match but
 * its last three chords do, and "no results" is a bad thing to say on stage.
 */
export async function bestSongMatch(degrees, { minLength = 2 } = {}) {
  for (let len = degrees.length; len >= minLength; len--) {
    const cp = degrees.slice(degrees.length - len).join(",");
    try {
      const songs = await songsFor(cp);
      if (songs.length) return { cp, matchedLength: len, songs };
    } catch {
      /* try a shorter path */
    }
  }
  return { cp: null, matchedLength: 0, songs: [] };
}

/**
 * Call this on mount with the progressions you plan to play in the demo.
 * Populates the cache so the live run never waits on the network.
 *
 * e.g. prewarm([[1,5,6,4], [6,4,1,5], [1,4], [2,5,1]])
 */
export async function prewarm(progressions) {
  const paths = new Set([""]);
  for (const prog of progressions) {
    for (let i = 1; i <= prog.length; i++) paths.add(prog.slice(0, i).join(","));
  }
  const results = await Promise.allSettled(
    [...paths].flatMap((cp) => [
      nextChordNodes(cp),
      cp ? songsFor(cp) : Promise.resolve([]),
    ])
  );
  return {
    requested: paths.size,
    failed: results.filter((r) => r.status === "rejected").length,
  };
}

export function clearCache() {
  nodeCache.clear();
  songCache.clear();
}
