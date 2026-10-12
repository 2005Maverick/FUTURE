"use client";
import { useEffect, useState } from "react";
import { supabaseBrowser } from "@/lib/supabase/client";

type Event = { id: number; at: string; level: string; kind: string; message: string | null };

const LEVEL_COLOR: Record<string, string> = { error: "text-red-600", warn: "text-amber-600", info: "", debug: "text-neutral-500" };

/** Live agent view: last 50 events, then new ones streamed via Supabase Realtime (RLS applies). */
export default function LiveEvents() {
  const [events, setEvents] = useState<Event[]>([]);
  const [status, setStatus] = useState("connecting");

  useEffect(() => {
    const supabase = supabaseBrowser();
    supabase.from("events").select("id,at,level,kind,message").order("id", { ascending: false }).limit(50)
      .then(({ data }) => setEvents((data ?? []) as Event[]));
    const channel = supabase
      .channel("events-live")
      .on("postgres_changes", { event: "INSERT", schema: "public", table: "events" }, (payload) => {
        setEvents((prev) => [payload.new as Event, ...prev].slice(0, 200));
      })
      .subscribe((s) => setStatus(s === "SUBSCRIBED" ? "live" : s.toLowerCase()));
    return () => { supabase.removeChannel(channel); };
  }, []);

  return (
    <section>
      <h2 className="mb-2 font-medium">Agent events <span className="ml-2 text-xs text-neutral-500">({status})</span></h2>
      <ul className="space-y-1 font-mono text-xs">
        {events.map((e) => (
          <li key={e.id} className={LEVEL_COLOR[e.level] ?? ""}>
            {new Date(e.at).toLocaleTimeString()} · {e.kind} · {e.message}
          </li>
        ))}
        {events.length === 0 && <li className="text-neutral-500">No events yet.</li>}
      </ul>
    </section>
  );
}
