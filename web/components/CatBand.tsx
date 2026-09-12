"use client";

/**
 * The HackStreet Bois.
 *
 * One cat design in six colours, rather than six drawings. A single shape reads
 * as a group at a glance and stays legible at avatar size, where fine detail
 * turns to mush anyway.
 */

export interface Cat {
  id: string;
  name: string;
  role: string;
  coat: string;
  belly: string;
  cheeks: string;
}

export const BAND: Cat[] = [
  { id: "biscuit",    name: "Biscuit",    role: "lead vocals", coat: "#ff9ed2", belly: "#ffd9ee", cheeks: "#ff6fae" },
  { id: "domino",     name: "Domino",     role: "keys",        coat: "#8ed0ff", belly: "#d4ecff", cheeks: "#5bb4f5" },
  { id: "pepper",     name: "Pepper",     role: "bass",        coat: "#8df3c4", belly: "#cdfae6", cheeks: "#54d9a1" },
  { id: "waffles",    name: "Waffles",    role: "drums",       coat: "#ffd382", belly: "#ffeccb", cheeks: "#f0b44f" },
  { id: "luna",       name: "Luna",       role: "synths",      coat: "#c4a8ff", belly: "#e6dbff", cheeks: "#9d7bf0" },
  { id: "clementine", name: "Clementine", role: "harmonies",   coat: "#ff97a8", belly: "#ffd5db", cheeks: "#f56e85" },
];

export function CatFace({
  cat, size = 76, decorative = false,
}: { cat: Cat; size?: number; decorative?: boolean }) {
  return (
    <svg
      viewBox="0 0 100 100"
      width={size}
      height={size}
      /* Decorative wherever the name sits beside it: announcing both would say
         everything twice. */
      role={decorative ? undefined : "img"}
      aria-hidden={decorative ? true : undefined}
      aria-label={decorative ? undefined : `${cat.name}, ${cat.role}`}
    >
      <path d="M20 36 L23 9 L45 24 Z" fill={cat.coat} />
      <path d="M80 36 L77 9 L55 24 Z" fill={cat.coat} />
      <path d="M26 32 L28 17 L39 25 Z" fill={cat.belly} />
      <path d="M74 32 L72 17 L61 25 Z" fill={cat.belly} />

      <ellipse cx="50" cy="52" rx="32" ry="29" fill={cat.coat} />
      <ellipse cx="50" cy="60" rx="20" ry="16" fill={cat.belly} />

      {/* Closed, happy eyes: friendlier than staring pupils, and they survive
          being shrunk to a 34px avatar. */}
      <path d="M32 48 q7 -8 14 0" fill="none" stroke="#2a1240" strokeWidth="3.4" strokeLinecap="round" />
      <path d="M54 48 q7 -8 14 0" fill="none" stroke="#2a1240" strokeWidth="3.4" strokeLinecap="round" />

      <ellipse cx="27" cy="58" rx="6" ry="4" fill={cat.cheeks} opacity="0.75" />
      <ellipse cx="73" cy="58" rx="6" ry="4" fill={cat.cheeks} opacity="0.75" />

      <path d="M50 58 l-4.5 -3.6 h9 Z" fill="#2a1240" />
      <path d="M50 58 v3 M50 61 q-4.5 4 -8.5 0.6 M50 61 q4.5 4 8.5 0.6"
            stroke="#2a1240" strokeWidth="2.2" fill="none" strokeLinecap="round" />

      <g stroke="#2a1240" strokeWidth="1.9" strokeLinecap="round" opacity="0.6">
        <line x1="24" y1="52" x2="10" y2="49" />
        <line x1="24" y1="57" x2="10" y2="58" />
        <line x1="76" y1="52" x2="90" y2="49" />
        <line x1="76" y1="57" x2="90" y2="58" />
      </g>

      {/* A music note, because this is a band. */}
      <g fill={cat.cheeks}>
        <ellipse cx="79" cy="86" rx="5" ry="4" transform="rotate(-18 79 86)" />
        <rect x="82.5" y="70" width="2.6" height="16" rx="1.3" />
        <path d="M85.1 70 q6 1.5 6 6 q-2.5 -3.5 -6 -3 Z" />
      </g>
    </svg>
  );
}

export default function CatBand() {
  return (
    <figure className="band">
      <ul className="band-row">
        {BAND.map((cat) => (
          <li key={cat.id} className="band-member">
            <CatFace cat={cat} decorative />
            <span className="band-name">{cat.name}</span>
            <span className="band-role">{cat.role}</span>
          </li>
        ))}
      </ul>
      <figcaption className="sub" style={{ margin: "0.9rem 0 0" }}>
        The HackStreet Bois — four toms, two queens, one chord progression.
      </figcaption>
    </figure>
  );
}
