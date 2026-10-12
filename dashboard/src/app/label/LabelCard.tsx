"use client";
import { useActionState } from "react";
import { saveLabel, type LabelResult } from "./actions";
import type { LabelItem } from "@/lib/labels";

export default function LabelCard({ item }: { item: LabelItem }) {
  const [state, action, pending] = useActionState<LabelResult, FormData>(saveLabel, { ok: false });
  if (state.ok) return null; // labelled: drop from the queue
  return (
    <form action={action} className="space-y-2 rounded-md border border-neutral-200 p-4 dark:border-neutral-800">
      <input type="hidden" name="target_id" value={item.id} />
      <a href={item.url} target="_blank" rel="noreferrer noopener" className="font-medium hover:underline">
        {item.org} — {item.title}
      </a>
      <p className="text-xs text-neutral-500">{item.location}</p>
      <p className="line-clamp-4 text-sm text-neutral-700 dark:text-neutral-300">{item.excerpt}</p>
      <div className="flex flex-wrap items-center gap-4 text-sm">
        <span>Worth applying?</span>
        <label><input type="radio" name="worth_applying" value="yes" required /> yes</label>
        <label><input type="radio" name="worth_applying" value="no" /> no</label>
        <span className="ml-4">Fit</span>
        {[1, 2, 3, 4, 5].map((n) => (
          <label key={n}><input type="radio" name="rating" value={n} required /> {n}</label>
        ))}
      </div>
      <input name="reason" placeholder="One line why (optional, helps calibration)"
             className="w-full rounded-md border border-neutral-300 bg-transparent px-2 py-1 text-sm dark:border-neutral-700" />
      <button disabled={pending} className="rounded-md bg-neutral-900 px-3 py-1 text-sm text-white disabled:opacity-50 dark:bg-white dark:text-neutral-900">
        {pending ? "Saving…" : "Save"}
      </button>
      {state.error && <p className="text-sm text-red-600">{state.error}</p>}
    </form>
  );
}
