import { Suspense } from "react";
import { loadLabelQueue } from "@/lib/labels";
import LabelCard from "./LabelCard";

export default function LabelPage() {
  return (
    <div className="space-y-4">
      <h1 className="text-xl font-semibold">Label (calibration)</h1>
      <p className="text-sm text-neutral-500">
        Rate each role on your own judgement. The Evaluator&apos;s scores are hidden on purpose so they don&apos;t anchor you.
        40 labels set the baseline for checking the Evaluator against you (E-03).
      </p>
      <Suspense fallback={<p className="text-sm text-neutral-500">Loading…</p>}>
        <Queue />
      </Suspense>
    </div>
  );
}

async function Queue() {
  const { items, labelled, error } = await loadLabelQueue();
  return (
    <>
      <p className="text-sm">Labelled so far: <b>{labelled}</b> / 40</p>
      {error && <p className="text-sm text-red-600">Could not load: {error}</p>}
      {items.length === 0 && !error && <p className="text-sm text-neutral-500">Nothing to label yet.</p>}
      <div className="space-y-3">{items.map((i) => <LabelCard key={i.id} item={i} />)}</div>
    </>
  );
}
