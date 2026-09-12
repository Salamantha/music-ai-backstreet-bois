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
}

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


/** Per-channel summary of a take, so a flooded or drum-heavy stream is obvious. */
export function channelStats(events: MidiEvent[]): ChannelStats[] {
  const byChannel = new Map<number, ChannelStats>();
  const sounding = new Map<number, Set<number>>();

  for (const e of events) {
    const ch = e.c ?? 1;
    let s = byChannel.get(ch);
    if (!s) {
      s = {
        channel: ch, noteOns: 0, noteOffs: 0, ccs: 0,
        lowPitch: 127, highPitch: 0, maxSimultaneous: 0,
      };
      byChannel.set(ch, s);
      sounding.set(ch, new Set());
    }
    const held = sounding.get(ch)!;

    if (e.k === "cc") { s.ccs++; continue; }
    if (e.p === undefined) continue;

    if (e.k === "on") {
      s.noteOns++;
      s.lowPitch = Math.min(s.lowPitch, e.p);
      s.highPitch = Math.max(s.highPitch, e.p);
      held.add(e.p);
      s.maxSimultaneous = Math.max(s.maxSimultaneous, held.size);
    } else {
      s.noteOffs++;
      held.delete(e.p);
    }
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
 * Excludes GM channel 10 (percussion) and channels that never sound more than
 * one note at a time, which are melody or bass lines rather than chords.
 */
export function suggestHarmonyChannels(stats: ChannelStats[]): Set<number> {
  const musical = stats.filter(
    (s) => s.channel !== DRUM_CHANNEL && s.noteOns > 0,
  );
  const polyphonic = musical.filter((s) => s.maxSimultaneous >= 3);
  const chosen = polyphonic.length > 0 ? polyphonic : musical;
  return new Set(chosen.map((s) => s.channel));
}
