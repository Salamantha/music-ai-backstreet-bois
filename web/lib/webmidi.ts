/**
 * Web MIDI capture for the AlphaTheta ChordCat.
 *
 * Browser support is the main constraint: Chrome/Edge 43+ and Firefox 108+ ship
 * the Web MIDI API, Safari does not on any platform and has no roadmap to. We
 * only need note-on/note-off and the sustain pedal, so access is requested
 * WITHOUT sysex -- that avoids a second, scarier permission prompt and the
 * fingerprinting concerns that keep Safari away.
 */

export type MidiEventKind = "on" | "off" | "cc";

/** Wire format posted to the backend. Deliberately terse: takes get long. */
export interface MidiEvent {
  k: MidiEventKind;
  t: number;
  p?: number;
  v?: number;
  n?: number;
  /** MIDI channel, 1-16. Kept so tracks can be separated before analysis. */
  c?: number;
}

/** A raw message, retained for the monitor so we can see what the device sends. */
export interface RawMessage {
  t: number;
  bytes: number[];
  channel: number;
  type: string;
}

export interface ChannelStats {
  channel: number;
  noteOns: number;
  noteOffs: number;
  ccs: number;
  lowPitch: number;
  highPitch: number;
  /** Largest number of notes sounding together on this channel. */
  maxSimultaneous: number;
  /** Distinct onsets, after grouping notes that start together. */
  onsetGroups: number;
  /** Most common number of notes sharing an onset -- the real chord signal. */
  modalGroupSize: number;
  /** Share of onsets that carry three or more notes. */
  chordalRatio: number;
}

/** Notes starting within this of each other are one voicing, not several. */
const ONSET_GROUP_MS = 15;

/** General MIDI reserves channel 10 for percussion. */
export const DRUM_CHANNEL = 10;

export interface MidiPort {
  id: string;
  name: string;
  manufacturer: string;
}

export type MidiSupport =
  | { supported: true }
  | { supported: false; reason: string };

const NOTE_OFF = 0x80;
const NOTE_ON = 0x90;
const CONTROL_CHANGE = 0xb0;
const SUSTAIN_CC = 64;

export function checkSupport(): MidiSupport {
  if (typeof navigator === "undefined") {
    return { supported: false, reason: "Not running in a browser." };
  }
  // TypeScript's lib.dom declares requestMIDIAccess as always present, so a
  // plain `in` check narrows `navigator` to never. It genuinely is absent in
  // Safari, so probe through an unnarrowed reference.
  const nav = navigator as Navigator & {
    requestMIDIAccess?: Navigator["requestMIDIAccess"];
  };
  if (typeof nav.requestMIDIAccess !== "function") {
    const ua = nav.userAgent;
    const isSafari = /^((?!chrome|android).)*safari/i.test(ua);
    return {
      supported: false,
      reason: isSafari
        ? "Safari does not implement the Web MIDI API on any platform. Open this page in Chrome, Edge, or Firefox 108+."
        : "This browser does not support the Web MIDI API. Try Chrome, Edge, or Firefox 108+.",
    };
  }
  return { supported: true };
}

/** A port that looks like a ChordCat, so we can preselect it. */
export function looksLikeChordcat(port: MidiPort): boolean {
  return /chordcat|chord\s*cat/i.test(`${port.name} ${port.manufacturer}`);
}

export class MidiCapture {
  private access: MIDIAccess | null = null;
  private input: MIDIInput | null = null;
  private events: MidiEvent[] = [];
  private raw: RawMessage[] = [];
  private startedAt = 0;
  private listeners = new Set<(e: MidiEvent, all: MidiEvent[]) => void>();
  private rawListeners = new Set<(m: RawMessage) => void>();
  /** Cap retained raw messages; a running sequencer produces thousands. */
  private rawLimit = 400;

  async connect(): Promise<MidiPort[]> {
    const support = checkSupport();
    if (!support.supported) throw new Error(support.reason);

    // sysex:false keeps this to a single, mild permission prompt.
    this.access = await navigator.requestMIDIAccess({ sysex: false });
    return this.ports();
  }

  ports(): MidiPort[] {
    if (!this.access) return [];
    return Array.from(this.access.inputs.values()).map((i) => ({
      id: i.id,
      name: i.name ?? "unnamed",
      manufacturer: i.manufacturer ?? "",
    }));
  }

  onStateChange(cb: () => void): void {
    if (this.access) this.access.onstatechange = () => cb();
  }

  select(portId: string): void {
    if (!this.access) throw new Error("call connect() first");
    if (this.input) this.input.onmidimessage = null;
    const port = this.access.inputs.get(portId);
    if (!port) throw new Error(`no MIDI input with id ${portId}`);
    this.input = port;
    port.onmidimessage = (msg) => this.handle(msg);
  }

  subscribe(cb: (e: MidiEvent, all: MidiEvent[]) => void): () => void {
    this.listeners.add(cb);
    return () => this.listeners.delete(cb);
  }

  subscribeRaw(cb: (m: RawMessage) => void): () => void {
    this.rawListeners.add(cb);
    return () => this.rawListeners.delete(cb);
  }

  start(): void {
    this.events = [];
    this.raw = [];
    this.startedAt = performance.now();
  }

  /**
   * Continue an existing take rather than replacing it.
   *
   * The time origin is rebased so new events carry on from where the previous
   * pass left off. Without that, resuming would stamp fresh events at t=0 and
   * interleave them with the earlier ones, scrambling the order segmentation
   * depends on. The gap while capture was stopped is deliberately collapsed to
   * a single chord's length -- the player paused, they did not hold a chord for
   * three minutes.
   */
  resume(gapMs = 600): void {
    if (this.events.length === 0) {
      this.start();
      return;
    }
    const last = this.events[this.events.length - 1].t;
    this.startedAt = performance.now() - (last + gapMs);
  }

  hasCapture(): boolean {
    return this.events.length > 0;
  }

  rawMessages(): RawMessage[] {
    return [...this.raw];
  }

  /** Elapsed ms, or 0 before the first start(). */
  elapsed(): number {
    return this.startedAt ? performance.now() - this.startedAt : 0;
  }

  snapshot(): MidiEvent[] {
    return [...this.events];
  }

  clear(): void {
    this.events = [];
    this.startedAt = performance.now();
  }

  disconnect(): void {
    if (this.input) this.input.onmidimessage = null;
    this.input = null;
  }

  private handle(msg: MIDIMessageEvent): void {
    const data = msg.data;
    if (!data || data.length < 2) return;

    const status = data[0] & 0xf0;
    const channel = (data[0] & 0x0f) + 1;
    // Timestamps come from performance.now()'s clock, same as startedAt.
    const t = Math.max(0, (msg.timeStamp || performance.now()) - this.startedAt);

    let event: MidiEvent | null = null;
    let type = `status 0x${status.toString(16)}`;
    if (status === NOTE_ON) {
      // Running status: note-on with velocity 0 is really a note-off.
      event = data[2] > 0
        ? { k: "on", t, p: data[1], v: data[2], c: channel }
        : { k: "off", t, p: data[1], c: channel };
      type = data[2] > 0 ? "noteOn" : "noteOff(vel0)";
    } else if (status === NOTE_OFF) {
      event = { k: "off", t, p: data[1], c: channel };
      type = "noteOff";
    } else if (status === CONTROL_CHANGE) {
      type = `cc${data[1]}`;
      if (data[1] === SUSTAIN_CC) {
        event = { k: "cc", t, n: SUSTAIN_CC, v: data[2], c: channel };
      }
    }

    const record: RawMessage = { t, bytes: [...data], channel, type };
    this.raw.push(record);
    if (this.raw.length > this.rawLimit) this.raw.shift();
    for (const cb of this.rawListeners) cb(record);

    if (!event) return;

    if (this.startedAt === 0) this.startedAt = performance.now();
    this.events.push(event);
    for (const cb of this.listeners) cb(event, this.events);
  }
}

/** Notes currently held down, derived from the event list. */
export function heldNotes(events: MidiEvent[]): number[] {
  const held = new Set<number>();
  for (const e of events) {
    if (e.p === undefined) continue;
    if (e.k === "on") held.add(e.p);
    else if (e.k === "off") held.delete(e.p);
  }
  return [...held].sort((a, b) => a - b);
}

const NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"];

export function noteName(pitch: number): string {
  return `${NAMES[pitch % 12]}${Math.floor(pitch / 12) - 1}`;
}


/**
 * Per-channel summary of a take.
 *
 * The load-bearing statistic is `modalGroupSize` -- how many notes usually share
 * an onset. Sustained overlap is not a usable signal: a legato melody line keeps
 * several notes ringing at once and looks every bit as "polyphonic" as a chord
 * track, which is exactly how a lead line can be mistaken for harmony.
 */
export function channelStats(events: MidiEvent[]): ChannelStats[] {
  const byChannel = new Map<number, ChannelStats>();
  const sounding = new Map<number, Set<number>>();
  const groupSizes = new Map<number, number[]>();
  const lastOnset = new Map<number, number>();

  for (const e of events) {
    const ch = e.c ?? 1;
    let s = byChannel.get(ch);
    if (!s) {
      s = {
        channel: ch, noteOns: 0, noteOffs: 0, ccs: 0,
        lowPitch: 127, highPitch: 0, maxSimultaneous: 0,
        onsetGroups: 0, modalGroupSize: 0, chordalRatio: 0,
      };
      byChannel.set(ch, s);
      sounding.set(ch, new Set());
      groupSizes.set(ch, []);
    }
    const held = sounding.get(ch)!;
    const sizes = groupSizes.get(ch)!;

    if (e.k === "cc") { s.ccs++; continue; }
    if (e.p === undefined) continue;

    if (e.k === "on") {
      s.noteOns++;
      s.lowPitch = Math.min(s.lowPitch, e.p);
      s.highPitch = Math.max(s.highPitch, e.p);
      held.add(e.p);
      s.maxSimultaneous = Math.max(s.maxSimultaneous, held.size);

      const previous = lastOnset.get(ch);
      if (previous !== undefined && e.t - previous <= ONSET_GROUP_MS) {
        sizes[sizes.length - 1] += 1;
      } else {
        sizes.push(1);
        lastOnset.set(ch, e.t);
      }
    } else {
      s.noteOffs++;
      held.delete(e.p);
    }
  }

  for (const [ch, sizes] of groupSizes) {
    const s = byChannel.get(ch)!;
    s.onsetGroups = sizes.length;
    const histogram = new Map<number, number>();
    for (const n of sizes) histogram.set(n, (histogram.get(n) ?? 0) + 1);
    let best = 0, bestCount = -1;
    for (const [size, count] of histogram) {
      if (count > bestCount || (count === bestCount && size > best)) {
        best = size;
        bestCount = count;
      }
    }
    s.modalGroupSize = best;
    const chordal = sizes.filter((n) => n >= 3).reduce((a, b) => a + b, 0);
    s.chordalRatio = s.noteOns ? chordal / s.noteOns : 0;
  }

  return [...byChannel.values()].sort((a, b) => a.channel - b.channel);
}

/** Keep only the selected channels. */
export function filterChannels(events: MidiEvent[], keep: Set<number>): MidiEvent[] {
  return events.filter((e) => keep.has(e.c ?? 1));
}

/**
 * Guess which channels carry harmony.
 *
 * A channel qualifies when its *typical* onset carries three or more notes.
 * Verified against a real ChordCat capture: of eight running sequencer tracks,
 * only the chord track had a modal onset size above one -- every other track was
 * a melody, bass or percussion line, and merging them into the chord track is
 * what makes identification produce nonsense.
 */
export function suggestHarmonyChannels(stats: ChannelStats[]): Set<number> {
  const musical = stats.filter(
    (s) => s.channel !== DRUM_CHANNEL && s.noteOns > 0,
  );
  const chordal = musical.filter((s) => s.modalGroupSize >= 3);
  if (chordal.length > 0) return new Set(chordal.map((s) => s.channel));
  // Nothing is clearly chordal; fall back to whatever is most nearly so, so the
  // user has something selected rather than an empty analysis.
  const best = musical
    .slice()
    .sort((a, b) => b.chordalRatio - a.chordalRatio)[0];
  return new Set(best ? [best.channel] : []);
}
