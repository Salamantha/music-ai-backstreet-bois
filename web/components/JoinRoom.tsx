"use client";

import { useState } from "react";
import { joinRoom, type AnalyzeResponse, type JoinRoomResponse } from "@/lib/api";
import { INSTRUMENTS, loadMember, memberId, saveMember } from "@/lib/room";
import { CityInput } from "./CityInput";

export function JoinRoom({
  result, onJoined,
}: {
  result: AnalyzeResponse;
  onJoined: (room: JoinRoomResponse) => void;
}) {
  const remembered = loadMember();
  const [name, setName] = useState(remembered?.name ?? "");
  const [city, setCity] = useState(remembered?.city ?? "");
  const [instrument, setInstrument] = useState(remembered?.instrument ?? "keys");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const canSubmit = name.trim().length > 0 && result.profile !== null && !busy;

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!canSubmit || !result.profile) return;
    setBusy(true);
    setError("");
    const member = { name: name.trim(), city: city.trim(), instrument };
    try {
      const room = await joinRoom({
        client_id: memberId(member),
        ...member,
        signature_progression: result.cp,
        mode: result.key?.mode ?? "major",
        profile: result.profile,
      });
      saveMember(member);
      onJoined(room);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="panel join-room">
      <h2>Musicians you&apos;d click with</h2>
      <p className="sub">
        Add yourself to the room so people can find you, and we&apos;ll show
        you who plays closest to what you just played.
      </p>
      <form className="join-form" onSubmit={submit}>
        <div className="join-field">
          <label htmlFor="join-name">Name</label>
          <input
            id="join-name"
            className="mono join-input"
            placeholder="What people call you"
            value={name}
            onChange={(e) => setName(e.target.value)}
            maxLength={80}
            autoComplete="name"
          />
        </div>
        <div className="join-field">
          <label htmlFor="join-city">City</label>
          <CityInput id="join-city" value={city} onChange={setCity} placeholder="Where you play" />
        </div>
        <div className="join-field">
          <label htmlFor="join-instrument">Instrument</label>
          <select
            id="join-instrument"
            value={instrument}
            onChange={(e) => setInstrument(e.target.value)}
          >
            {INSTRUMENTS.map((i) => <option key={i} value={i}>{i}</option>)}
          </select>
        </div>
        <div className="join-actions">
          <button type="submit" className="primary" disabled={!canSubmit}>
            {busy ? "Joining…" : "Join the room"}
          </button>
        </div>
      </form>
      {error && <p className="error" style={{ margin: "0.75rem 0 0" }}>{error}</p>}
    </div>
  );
}
