"use client";

import { useEffect, useState } from "react";
import { supabase } from "@/lib/supabase";
import { CityInput } from "@/components/CityInput";

interface User {
  id: number;
  created_at: string;
  name: string;
  city: string | null;
}

export default function TestPage() {
  const [users, setUsers] = useState<User[]>([]);
  const [name, setName] = useState("");
  const [city, setCity] = useState("");
  const [loading, setLoading] = useState(true);
  const [adding, setAdding] = useState(false);
  const [error, setError] = useState("");

  async function loadUsers() {
    setLoading(true);
    setError("");
    const { data, error } = await supabase
      .from("users")
      .select("*")
      .order("id", { ascending: false });
    if (error) setError(error.message);
    else setUsers(data as User[]);
    setLoading(false);
  }

  useEffect(() => {
    void loadUsers();
  }, []);

  async function addUser(e: React.FormEvent) {
    e.preventDefault();
    if (!name.trim()) return;
    setAdding(true);
    setError("");
    const { error } = await supabase
      .from("users")
      .insert({ name: name.trim(), city: city.trim() || null });
    if (error) setError(error.message);
    else {
      setName("");
      setCity("");
      await loadUsers();
    }
    setAdding(false);
  }

  return (
    <main>
      <h1>Supabase test</h1>
      <p className="sub">Reads from and writes to the `users` table directly from the browser.</p>

      <div className="panel">
        <h2>Add user</h2>
        <form className="row" onSubmit={addUser}>
          <input
            className="mono"
            style={{
              font: "inherit", background: "var(--panel-2)", color: "var(--text)",
              border: "1px solid var(--line)", borderRadius: 8, padding: "9px 11px", flex: 1,
            }}
            placeholder="Name"
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
          <CityInput value={city} onChange={setCity} />
          <button type="submit" className="primary" disabled={adding || !name.trim()}>
            {adding ? "Adding…" : "Add"}
          </button>
        </form>
      </div>

      {error && (
        <div className="panel"><p className="error" style={{ margin: 0 }}>{error}</p></div>
      )}

      <div className="panel">
        <h2>Users</h2>
        {loading ? (
          <p style={{ margin: 0 }}>Loading…</p>
        ) : users.length === 0 ? (
          <p style={{ margin: 0 }}>No users yet.</p>
        ) : (
          <table>
            <thead>
              <tr><th>ID</th><th>Name</th><th>City</th><th>Created at</th></tr>
            </thead>
            <tbody>
              {users.map((u) => (
                <tr key={u.id}>
                  <td>{u.id}</td>
                  <td>{u.name}</td>
                  <td>{u.city ?? ""}</td>
                  <td>{new Date(u.created_at).toLocaleString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </main>
  );
}
