const MEMBER_KEY = "chordcat_member";

export interface Member {
  name: string;
  city: string;
  instrument: string;
}

export const INSTRUMENTS = [
  "keys", "guitar", "bass", "drums", "vocals", "synth", "producer", "other",
] as const;

/**
 * Identity follows the person, not the browser: the same name and city always
 * lands on the same row, so replaying updates you while a new name on a shared
 * laptop creates someone new.
 */
export function memberId(member: Member): string {
  const key = `${member.name}|${member.city}`.trim().toLowerCase();
  let h = 0x811c9dc5;
  for (const ch of key) {
    h ^= ch.charCodeAt(0);
    h = Math.imul(h, 0x01000193) >>> 0;
  }
  const slug = member.name.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "").slice(0, 24);
  return `${slug || "player"}-${h.toString(16).padStart(8, "0")}`;
}

export function loadMember(): Member | null {
  try {
    const raw = localStorage.getItem(MEMBER_KEY);
    return raw ? (JSON.parse(raw) as Member) : null;
  } catch {
    return null;
  }
}

export function saveMember(member: Member): void {
  try {
    localStorage.setItem(MEMBER_KEY, JSON.stringify(member));
  } catch {
    // storage unavailable; the form just won't be prefilled next time
  }
}
