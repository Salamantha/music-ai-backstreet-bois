"use client";

/**
 * Domino at the piano: the band's keys player, and the app's mascot.
 *
 * Drawn larger and with more detail than the wallpaper cats, since this one is
 * looked at rather than glanced past.
 */
export default function PianoCat({
  size = 190, playing = false,
}: {
  size?: number;
  /** Bang the keys. Same cat either way -- he just gets to move. */
  playing?: boolean;
}) {
  const on = playing ? " pc-on" : "";
  return (
    <svg
      viewBox="0 0 200 170"
      width={size}
      height={(size * 170) / 200}
      role="img"
      aria-label={
        playing
          ? "Domino, the band's keyboard player, hammering away at a piano"
          : "Domino, the band's keyboard player, at a piano"
      }
    >
      {/* Sparkles, because he is the favourite */}
      <g fill="#ffd382" opacity="0.9" className={`pc-sparkles${on}`}>
        <path d="M34 20 l2.4 6.2 6.2 2.4 -6.2 2.4 -2.4 6.2 -2.4 -6.2 -6.2 -2.4 6.2 -2.4 Z" />
        <path d="M168 34 l1.8 4.6 4.6 1.8 -4.6 1.8 -1.8 4.6 -1.8 -4.6 -4.6 -1.8 4.6 -1.8 Z" />
        <path d="M156 12 l1.2 3 3 1.2 -3 1.2 -1.2 3 -1.2 -3 -3 -1.2 3 -1.2 Z" />
      </g>

      {/* Floating notes. While he plays they rise and fade, one after another. */}
      <g fill="#8ed0ff" opacity="0.85">
        <g className={`pc-note pc-note-1${on}`}>
          <ellipse cx="52" cy="46" rx="4.4" ry="3.5" transform="rotate(-18 52 46)" />
          <rect x="55.2" y="32" width="2.3" height="14" rx="1.15" />
        </g>
        <g className={`pc-note pc-note-2${on}`}>
          <ellipse cx="146" cy="60" rx="3.8" ry="3" transform="rotate(-18 146 60)" />
          <rect x="148.8" y="48" width="2" height="12" rx="1" />
        </g>
        <g className={`pc-note pc-note-3${on}`} opacity={playing ? undefined : 0}>
          <ellipse cx="100" cy="40" rx="3.4" ry="2.7" transform="rotate(-18 100 40)" />
          <rect x="102.4" y="29" width="1.9" height="11" rx="0.95" />
        </g>
      </g>

      <g className={`pc-head${on}`}>
      {/* Ears */}
      <path d="M66 62 L69 28 L96 48 Z" fill="#8ed0ff" />
      <path d="M134 62 L131 28 L104 48 Z" fill="#8ed0ff" />
      <path d="M73 56 L75 38 L88 48 Z" fill="#d4ecff" />
      <path d="M127 56 L125 38 L112 48 Z" fill="#d4ecff" />

      {/* Head */}
      <ellipse cx="100" cy="80" rx="40" ry="36" fill="#8ed0ff" />
      <ellipse cx="100" cy="90" rx="25" ry="20" fill="#d4ecff" />

      {/* Happy closed eyes */}
      <path d="M77 74 q9 -10 18 0" fill="none" stroke="#2a1240" strokeWidth="4" strokeLinecap="round" />
      <path d="M105 74 q9 -10 18 0" fill="none" stroke="#2a1240" strokeWidth="4" strokeLinecap="round" />

      <ellipse cx="70" cy="88" rx="7.5" ry="5" fill="#5bb4f5" opacity="0.75" />
      <ellipse cx="130" cy="88" rx="7.5" ry="5" fill="#5bb4f5" opacity="0.75" />

      <path d="M100 88 l-5.5 -4.4 h11 Z" fill="#2a1240" />
      <path d="M100 88 v3.6 M100 91.6 q-5.5 5 -10.5 0.8 M100 91.6 q5.5 5 10.5 0.8"
            stroke="#2a1240" strokeWidth="2.6" fill="none" strokeLinecap="round" />

      <g stroke="#2a1240" strokeWidth="2.2" strokeLinecap="round" opacity="0.6">
        <line x1="62" y1="84" x2="44" y2="80" />
        <line x1="62" y1="90" x2="44" y2="92" />
        <line x1="138" y1="84" x2="156" y2="80" />
        <line x1="138" y1="90" x2="156" y2="92" />
      </g>

      {/* A little bow tie: he is the frontman of the keys */}
      <path d="M100 116 l-13 -8 v16 Z" fill="#ff9ed2" />
      <path d="M100 116 l13 -8 v16 Z" fill="#ff9ed2" />
      <circle cx="100" cy="116" r="4" fill="#ff6fae" />

      </g>

      {/* Piano */}
      <rect x="22" y="128" width="156" height="30" rx="7" fill="#2d2357" />
      <rect x="26" y="132" width="148" height="21" rx="4" fill="#f6f0ff" />
      {Array.from({ length: 14 }, (_, i) => (
        <rect key={i} x={26 + i * 10.6} y="132" width="1.5" height="21" fill="#2d2357" />
      ))}
      {[0, 1, 3, 4, 5, 7, 8, 10, 11, 12].map((i) => (
        <rect key={i} x={32.5 + i * 10.6} y="132" width="6" height="12.5" rx="1.5" fill="#2a1240" />
      ))}

      {/* The keys he is actually hitting, lit under each paw. */}
      <g fill="#ff9ed2" opacity="0">
        <rect className={`pc-hit pc-hit-l${on}`} x="62" y="132" width="11" height="21" rx="2" />
        <rect className={`pc-hit pc-hit-r${on}`} x="126" y="132" width="11" height="21" rx="2" />
      </g>

      {/* Paws on the keys */}
      <g className={`pc-paw pc-paw-l${on}`}>
        <ellipse cx="68" cy="130" rx="12" ry="8" fill="#8ed0ff" />
        <ellipse cx="68" cy="131" rx="6.5" ry="4" fill="#d4ecff" />
      </g>
      <g className={`pc-paw pc-paw-r${on}`}>
        <ellipse cx="132" cy="130" rx="12" ry="8" fill="#8ed0ff" />
        <ellipse cx="132" cy="131" rx="6.5" ry="4" fill="#d4ecff" />
      </g>
    </svg>
  );
}
