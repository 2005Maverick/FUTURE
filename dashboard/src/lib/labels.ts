import "server-only";
import { requireUser } from "@/lib/auth";

export type LabelItem = {
  id: string; title: string; org: string | null; location: string | null; url: string; excerpt: string;
};

/**
 * Items for the E-03 labelling set. The model's scores are deliberately NOT
 * returned: Pranav labels blind so his judgement isn't anchored by the
 * Evaluator's. Items are interleaved across the model's apply/maybe/skip
 * buckets so the set is balanced, not just the model's favourites.
 */
export async function loadLabelQueue(limit = 40) {
  const { supabase } = await requireUser();
  const [{ data: evals, error }, { data: labels }] = await Promise.all([
    supabase.from("evaluations").select("opportunity_id,recommendation,created_at").order("created_at", { ascending: false }).limit(1000),
    supabase.from("labels").select("target_id").eq("target_type", "opportunity"),
  ]);
  if (error) return { items: [] as LabelItem[], labelled: 0, error: error.message };
  const done = new Set((labels ?? []).map((l) => l.target_id as string));
  const buckets: Record<string, string[]> = { apply: [], maybe: [], skip: [] };
  for (const e of evals ?? []) {
    const id = e.opportunity_id as string;
    if (!done.has(id) && !Object.values(buckets).some((b) => b.includes(id))) buckets[e.recommendation as string]?.push(id);
  }
  const order: string[] = [];
  for (let i = 0; order.length < limit && i < 1000; i++) {
    for (const k of ["apply", "maybe", "skip"]) if (buckets[k][i] && order.length < limit) order.push(buckets[k][i]);
  }
  if (order.length === 0) return { items: [], labelled: done.size, error: undefined };
  const { data: opps } = await supabase.from("opportunities").select("id,title,org,location,url,details").in("id", order);
  const byId = new Map((opps ?? []).map((o) => [o.id as string, o]));
  const items = order.flatMap((id) => {
    const o = byId.get(id);
    if (!o) return [];
    const desc = String((o.details as { description?: string } | null)?.description ?? "");
    return [{ id, title: o.title as string, org: o.org as string | null, location: o.location as string | null,
              url: o.url as string, excerpt: desc.slice(0, 600) }];
  });
  return { items, labelled: done.size, error: undefined };
}
