"use client";

import { BAND, CatFace } from "./CatBand";

/**
 * Cats scattered behind the page.
 *
 * Positions are hard-coded rather than randomised: a random layout would differ
 * between the server render and the client one, and React would tear the whole
 * tree down over the mismatch.
 *
 * Opacity is held low enough that it costs nothing in contrast. Measured
 * against the brightest coat: at 0.10 the page background shifts from #181233
 * to about #2f253b, where body text still reads 13.0:1 and muted text 7.7:1 --
 * both well clear of the 4.5:1 that AA asks for.
 */
const SCATTER = [
  { top: "6%",  left: "3%",  size: 96,  rotate: -14, cat: 0 },
  { top: "14%", left: "88%", size: 74,  rotate: 12,  cat: 1 },
  { top: "31%", left: "-2%", size: 118, rotate: 8,   cat: 2 },
  { top: "44%", left: "93%", size: 88,  rotate: -9,  cat: 3 },
  { top: "58%", left: "6%",  size: 70,  rotate: 17,  cat: 4 },
  { top: "68%", left: "84%", size: 110, rotate: -12, cat: 5 },
  { top: "82%", left: "2%",  size: 84,  rotate: -6,  cat: 1 },
  { top: "91%", left: "90%", size: 66,  rotate: 14,  cat: 2 },
  { top: "24%", left: "46%", size: 60,  rotate: -18, cat: 4 },
  { top: "76%", left: "48%", size: 58,  rotate: 10,  cat: 0 },
];

export default function CatWallpaper() {
  return (
    <div className="wallpaper" aria-hidden="true">
      {SCATTER.map((s, i) => (
        <span
          key={i}
          style={{
            top: s.top,
            left: s.left,
            transform: `rotate(${s.rotate}deg)`,
          }}
        >
          <CatFace cat={BAND[s.cat]} size={s.size} decorative />
        </span>
      ))}
    </div>
  );
}
