"use client";

import { useState } from "react";

const API = process.env.NEXT_PUBLIC_API_URL;

type ConnectStatus = "idle" | "pending" | "mfa_required" | "success" | "error";

export default function ConnectGarminPage() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [mfaCode, setMfaCode] = useState("");
  const [attemptId, setAttemptId] = useState<string | null>(null);
  const [status, setStatus] = useState<ConnectStatus>("idle");
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  // NOTE: no Authorization header attached yet — see note in page.tsx.
  // Every one of these calls needs `Bearer ${clerkToken}` once Clerk is wired in.

  async function startConnect(e: React.FormEvent) {
    e.preventDefault();
    setStatus("pending");
    const res = await fetch(`${API}/api/v1/providers/garmin/connect`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, password }),
    });
    const data = await res.json();
    handleResult(data);
  }

  async function submitMfa(e: React.FormEvent) {
    e.preventDefault();
    if (!attemptId) return;
    const res = await fetch(`${API}/api/v1/providers/garmin/connect/${attemptId}/mfa`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ code: mfaCode }),
    });
    const data = await res.json();
    handleResult(data);
  }

  function handleResult(data: {
    attempt_id: string;
    status: ConnectStatus;
    error_message?: string;
  }) {
    setAttemptId(data.attempt_id);
    setStatus(data.status);
    if (data.status === "error") setErrorMessage(data.error_message ?? "Unknown error");
    if (data.status === "pending") {
      // Simple poll loop — replace with exponential backoff for production
      setTimeout(() => pollStatus(data.attempt_id), 2000);
    }
  }

  async function pollStatus(id: string) {
    const res = await fetch(`${API}/api/v1/providers/garmin/connect/${id}/status`);
    const data = await res.json();
    handleResult(data);
  }

  return (
    <main className="p-8 max-w-md mx-auto">
      <h1 className="text-xl font-medium mb-6">Connect Garmin</h1>

      {status !== "mfa_required" && status !== "success" && (
        <form onSubmit={startConnect} className="space-y-3">
          <input
            type="email"
            placeholder="Garmin email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className="w-full p-2 rounded bg-neutral-900 border border-neutral-800"
            required
          />
          <input
            type="password"
            placeholder="Garmin password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="w-full p-2 rounded bg-neutral-900 border border-neutral-800"
            required
          />
          <button className="w-full p-2 rounded bg-white text-black font-medium" disabled={status === "pending"}>
            {status === "pending" ? "Connecting… (can take 30-45s)" : "Connect"}
          </button>
        </form>
      )}

      {status === "mfa_required" && (
        <form onSubmit={submitMfa} className="space-y-3">
          <p className="text-sm text-neutral-400">Enter the MFA code Garmin sent you:</p>
          <input
            type="text"
            value={mfaCode}
            onChange={(e) => setMfaCode(e.target.value)}
            className="w-full p-2 rounded bg-neutral-900 border border-neutral-800"
            required
          />
          <button className="w-full p-2 rounded bg-white text-black font-medium">Submit code</button>
        </form>
      )}

      {status === "success" && (
        <p className="text-green-400">Connected. Go trigger a sync from the backend, then check the dashboard.</p>
      )}

      {errorMessage && <p className="text-red-400 text-sm mt-4">{errorMessage}</p>}
    </main>
  );
}
