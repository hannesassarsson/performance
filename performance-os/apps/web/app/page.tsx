"use client";

import { useEffect, useState } from "react";
import { useAuth } from "@clerk/nextjs";

type Activity = {
  id: string;
  activity_type: string;
  started_at: string | null;
  duration_seconds: number;
  distance_meters: number | null;
  avg_heart_rate: number | null;
};

export default function DashboardPage() {
  const { getToken, isLoaded, isSignedIn } = useAuth();
  const [activities, setActivities] = useState<Activity[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!isLoaded) return; // Clerk still figuring out auth state — wait
    if (!isSignedIn) {
      setError(null);
      return;
    }

    (async () => {
      try {
        const token = await getToken();
        const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/api/v1/activities`, {
          headers: { Authorization: `Bearer ${token}` },
        });
        if (!res.ok) throw new Error(`API returned ${res.status}`);
        setActivities(await res.json());
      } catch (err: any) {
        setError(err.message);
      }
    })();
  }, [isLoaded, isSignedIn, getToken]);

  return (
    <main className="p-8 max-w-2xl mx-auto">
      <h1 className="text-2xl font-medium mb-2">Performance OS</h1>
      <p className="text-neutral-400 mb-6">
        Skeleton dashboard — proves the pipeline (frontend → API → Postgres) works.
        The real dashboard design is Step 7.
      </p>

      {!isSignedIn && isLoaded && (
        <p className="text-neutral-500 text-sm mb-4">
          Sign in (top right) to see your data.
        </p>
      )}

      {isSignedIn && (
        <a
          href="/connect-garmin"
          className="inline-block mb-6 px-4 py-2 rounded-lg bg-white text-black text-sm font-medium"
        >
          Connect Garmin
        </a>
      )}

      {error && (
        <p className="text-red-400 text-sm mb-4">
          Couldn&apos;t load activities: {error}. Check NEXT_PUBLIC_API_URL and that
          the backend is running.
        </p>
      )}

      <div className="space-y-2">
        {isSignedIn && activities.length === 0 && !error && (
          <p className="text-neutral-500 text-sm">
            No activities yet — connect Garmin and trigger a sync.
          </p>
        )}
        {activities.map((a) => (
          <div key={a.id} className="border border-neutral-800 rounded-lg p-4">
            <div className="font-medium">{a.activity_type}</div>
            <div className="text-sm text-neutral-400">
              {a.started_at} · {Math.round(a.duration_seconds / 60)} min
              {a.distance_meters ? ` · ${(a.distance_meters / 1000).toFixed(2)} km` : ""}
              {a.avg_heart_rate ? ` · ${a.avg_heart_rate} bpm avg` : ""}
            </div>
          </div>
        ))}
      </div>
    </main>
  );
}
