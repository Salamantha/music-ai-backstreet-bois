# ChordCat Connect

**Play a few chords on any keyboard. It finds musicians who play like you so you can jam,
and suggests one new thing to try — explained in plain English.**

Built at a hackathon around the [AlphaTheta ChordCat](https://alphatheta.com/en/product/production/chordcat/gray/),
though any MIDI keyboard works.

## How it works

**1. You play.** Plug a MIDI device into your browser and play a chord progression. Nothing
is recorded until you press the button, and no audio is involved — just the notes.

**2. It works out what you played.** Ordinary code, not AI, figures out every chord, the key
you are in, and how you voice things: whether you invert chords, how wide you spread them,
how often you change. This part is deliberately not a language model, because a model that
names a chord you never played would be worse than useless.

**3. It finds the songs your playing resembles.** The progression is translated into the
notation Hooktheory uses, then matched against two separate song databases. Those songs come
back with artists and genres attached.

**4. That becomes your taste.** The songs you match tell us the genres, eras and moods you
gravitate toward. Combined with *how* you physically play — your voicings, your pacing, how
adventurous your harmony is — that becomes a profile of you as a player.

**5. You meet people.** Your profile is ranked against everyone else in the room. You get
names, cities, instruments, and a plain-English reason why the two of you should play
together.

### And while all that happens, it teaches you

A second part of the app watches the same playing and talks to you about it. It notices
something true about what you just played, offers one thing you have not tried, explains what
that does to your sound, and then stops talking.

It is built for someone who can hear what they want but cannot name any of it. No musical
term is ever used without its plain meaning in the same breath.

Two rules it will not break:

- **It never invents.** Every chord, key and number it says is checked against what was
  actually computed from your playing. If it tries to name a chord you did not play, that
  sentence is thrown away before you ever see it.
- **It never writes music for you.** It can hear everything you play, and it has no hands.
  It will explain an idea and show you where to find it — you play it.

It remembers the session too, so on your second take it tells you what changed rather than
repeating itself.

## Team

| | LinkedIn |
|---|---|
| Vishnu Sriram | <!-- add link --> |
| Omar Kassem | <!-- add link --> |
| Malcolm Malik | <!-- add link --> |
| Zoha | <!-- add link --> |
| Samantha Geller | <!-- add link --> |
| Viet Duc Kieu | <!-- add link --> |

## Run it

```bash
cp .env.example .env      # fill in the keys you have; it degrades gracefully without them
cd api && python3 -m venv .venv && . .venv/bin/activate && pip install -e '.[dev]'
```

```bash
cd api && uvicorn chordcat.main:app --reload     # http://localhost:8000
cd web && npm install && npm run dev             # http://localhost:3000
```

Open it in **Chrome, Edge, or Firefox 108+**. Safari does not implement the Web MIDI API on
any platform and has no plans to.

Two pages: `/` matches you with musicians, `/helper` tells you what to try next. No hardware
to hand? `/helper` has a recorded take you can run instead.

## Accessibility

Both senses of the word were design goals.

- **For people with no musical training.** The teaching layer explains rather than assumes.
- **For people with low vision.** The interface uses Atkinson Hyperlegible, and every colour
  was checked against its background rather than eyeballed — body text sits at 16:1, well
  clear of the WCAG AA threshold. Keyboard navigation, visible focus rings, screen-reader
  labels and a reduced-motion mode throughout.
