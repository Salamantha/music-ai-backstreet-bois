# Chordcat Voice

An external accessibility layer for the AlphaTheta Chordcat. The device ships with
no speech output — state is carried by LED colour and a small display — so a blind
or low-vision musician can't use it. This adds the missing voice over MIDI, without
touching the firmware.

Three things it does:

- **Announces** every chord played, in plain language.
- **Suggests** what comes next, using next-chord probabilities from Hooktheory's
  75,000-song corpus.
- **Harmonises** a hummed melody into chords and sends them back to the device.

## Install

```bash
npm i tonal pitchy
```

Drop `lib/` and `hooks/` into your Next.js app. Then:

```bash
cd server
pip install fastapi uvicorn httpx
export HOOKTHEORY_USER=you HOOKTHEORY_PASS=secret
uvicorn hooktheory_proxy:app --port 8000
```

Set `NEXT_PUBLIC_HOOKTHEORY_PROXY=http://localhost:8000` in `.env.local`.

## Use

```jsx
"use client";
import { useChordcatVoice } from "@/hooks/useChordcatVoice";

export default function Page() {
  const v = useChordcatVoice({ key: "C", mode: "major", bpm: 100 });

  return (
    <main>
      <button onClick={v.status === "listening" ? v.stop : v.start}>
        {v.status === "listening" ? "Stop" : "Start"}
      </button>
      {v.error && <p role="alert">{v.error}</p>}
      <p aria-live="polite">{v.progression.join(" · ")}</p>
    </main>
  );
}
```

Keyboard: **S** suggestion · **M** song match · **P** repeat progression ·
**H** hold to hum · **Esc** stop speaking.

## Files

| File | What it does |
|---|---|
| `lib/speech.js` | TTS with barge-in, rate control, phrase builders |
| `lib/midi.js` | Web MIDI in/out, device matching, chord playback |
| `lib/chords.js` | MIDI → chord names, chord → Hooktheory degree |
| `lib/pitch.js` | Mic → discrete sung notes, with smoothing |
| `lib/harmonize.js` | Melody → chord progression, key inference |
| `lib/hooktheory.js` | Cached client for the proxy |
| `hooks/useChordcatVoice.js` | Everything wired together |
| `server/hooktheory_proxy.py` | Auth, cache, rate-limit survival |

## Before you demo

1. **Chordcat firmware must be v1.30 or later.** Real-time recording of incoming
   MIDI landed there. On older firmware the hum feature will pass notes through
   but the device won't capture them.
2. **Use Chrome.** Web MIDI doesn't exist in Safari or Firefox.
3. **https:// or localhost.** Web MIDI and `getUserMedia` both require a secure
   context. A preview deployment is fine; a plain LAN IP is not.
4. **Pre-warm the cache**, then confirm it filled:
   ```bash
   curl "http://localhost:8000/api/prewarm?progressions=1,5,6,4;6,4,1,5;1,4,5"
   curl "http://localhost:8000/api/cache"
   ```
   Once warm, the demo runs with the wifi off.
5. **Unlock speech inside a click handler.** `start()` already does this; if you
   restructure, keep `unlockSpeech()` in the user-gesture call stack or the
   browser will silently swallow every utterance.
6. **Tune `clarityThreshold`** in `lib/pitch.js` to the room. 0.9 is a starting
   point; drop to 0.85 if the tracker ignores quiet humming, raise to 0.93 if it
   picks up chatter. Test in the actual presentation room if you can.

## Known limitations

Say these out loud if a judge asks. They're design decisions, not bugs.

- **Minor keys report in the relative major.** Hooktheory numbers everything
  against the major scale, so A minor comes back as vi–IV–I–V rather than
  i–VI–III–VII. Matches Hooktheory's own Trends page.
- **Diatonic triads only.** Inversions, slash chords and applied dominants can't
  be expressed in the `cp` param cleanly, so they're dropped rather than guessed
  at. `toChildPath` stops at the first chord it can't express.
- **Key is user-selected, not detected, in chord mode.** The player already set a
  key on the Chordcat. `inferKey()` exists for hum mode, where there's nothing
  else to go on.
- **Harmonisation is one chord per bar.** No passing chords, no secondary
  dominants, no voice leading beyond fixed root-position triads.
- **The fallback transition table is approximate.** It exists so a network
  failure doesn't kill the demo. Don't present its numbers as data.

## Licence note

This shares an *idea* with Charles Vestal's Move Everything — adding a screen
reader to a groovebox that shipped without one — but none of its code. Move
Everything is GPL-3.0 and runs on the Ableton Move's embedded Linux. The Chordcat
has closed firmware and no shell, so this takes the external-companion route
instead. Keep it that way unless you intend to relicense.
