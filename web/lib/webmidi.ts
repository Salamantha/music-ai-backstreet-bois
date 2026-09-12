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
}

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
  private startedAt = 0;
  private listeners = new Set<(e: MidiEvent, all: MidiEvent[]) => void>();

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

  start(): void {
    this.events = [];
    this.startedAt = performance.now();
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
    // Timestamps come from performance.now()'s clock, same as startedAt.
    const t = Math.max(0, (msg.timeStamp || performance.now()) - this.startedAt);

    let event: MidiEvent | null = null;
    if (status === NOTE_ON) {
      // Running status: note-on with velocity 0 is really a note-off.
      event = data[2] > 0
        ? { k: "on", t, p: data[1], v: data[2] }
        : { k: "off", t, p: data[1] };
    } else if (status === NOTE_OFF) {
      event = { k: "off", t, p: data[1] };
    } else if (status === CONTROL_CHANGE && data[1] === SUSTAIN_CC) {
      event = { k: "cc", t, n: SUSTAIN_CC, v: data[2] };
    }
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
