import { Suspense } from "react";
import LiveEvents from "@/components/LiveEvents";
import { loadLive } from "@/lib/data";

const STATUS_COLOR: Record<string, string> = {
  ok: "text-green-600", running: "text-blue-600", error: "text-red-600",
  budget_exhausted: "text-amber-600", skipped: "text-neutral-500",
};

export default function LivePage() {
  return (
    <div className="space-y-8">
      <h1 className="text-xl font-semibold">Live</h1>
      <Suspense fallback={<p className="text-sm text-neutral-500">Loading runs…</p>}>
        <Runs />
      </Suspense>
      <LiveEvents />
    </div>
  );
}

async function Runs() {
  const { runs, tokens24h, error } = await loadLive();
  return (
    <section>
      <p className="mb-3 text-sm text-neutral-500">Claude tokens used by the pipeline in the last 24h: {tokens24h.toLocaleString()}</p>
      {error && <p className="text-sm text-red-600">Could not load: {error}</p>}
      <h2 className="mb-2 font-medium">Recent runs</h2>
      <table className="w-full text-left text-sm">
        <thead className="text-neutral-500">
          <tr><th className="py-1">Started</th><th>Stage</th><th>Status</th><th>In → Out</th><th>Tokens</th><th>Error</th></tr>
        </thead>
        <tbody>
          {runs.map((r) => (
            <tr key={r.id} className="border-t border-neutral-200 dark:border-neutral-800">
              <td className="py-1 font-mono text-xs">{new Date(r.started_at).toLocaleString()}</td>
              <td>{r.stage}{r.agent ? ` · ${r.agent}` : ""}</td>
              <td className={STATUS_COLOR[r.status] ?? ""}>{r.status}</td>
              <td>{r.items_in} → {r.items_out}</td>
              <td>{r.tokens.toLocaleString()}</td>
              <td className="max-w-xs truncate text-red-600">{r.error ?? ""}</td>
            </tr>
          ))}
          {runs.length === 0 && <tr><td colSpan={6} className="py-3 text-neutral-500">No runs recorded yet.</td></tr>}
        </tbody>
      </table>
    </section>
  );
}
