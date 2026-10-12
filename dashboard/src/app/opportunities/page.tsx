import { Suspense } from "react";
import { loadOpportunities } from "@/lib/data";

export default function OpportunitiesPage() {
  return (
    <div>
      <h1 className="mb-1 text-xl font-semibold">Opportunities</h1>
      <p className="mb-4 text-sm text-neutral-500">Evaluated items, highest priority first.</p>
      <Suspense fallback={<p className="text-sm text-neutral-500">Loading…</p>}>
        <Table />
      </Suspense>
    </div>
  );
}

async function Table() {
  const { rows, error } = await loadOpportunities();
  return (
    <>
      {error && <p className="text-sm text-red-600">Could not load: {error}</p>}
      <table className="w-full text-left text-sm">
        <thead className="text-neutral-500">
          <tr><th className="py-1">Priority</th><th>Role</th><th>Location</th><th>Fit</th><th>Value</th><th>Rec.</th><th>Deadline</th></tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.url} className="border-t border-neutral-200 align-top dark:border-neutral-800">
              <td className="py-1">{r.priority ?? "–"}</td>
              <td><a href={r.url} target="_blank" rel="noreferrer noopener" className="hover:underline"><b>{r.org}</b> — {r.title}</a></td>
              <td className="max-w-[16rem] truncate">{r.location}</td>
              <td>{r.fit ?? "–"}</td>
              <td>{r.value ?? "–"}</td>
              <td>{r.recommendation}</td>
              <td>{r.deadline ?? "–"}</td>
            </tr>
          ))}
          {rows.length === 0 && !error && <tr><td colSpan={7} className="py-3 text-neutral-500">Nothing evaluated yet.</td></tr>}
        </tbody>
      </table>
    </>
  );
}
