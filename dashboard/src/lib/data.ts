import "server-only";
import { requireUser } from "@/lib/auth";

/**
 * Data loaders. Each one checks the session (requireUser) itself, so a page can
 * only render data after an authoritative auth check; RLS then limits rows to
 * the owner. Called from components rendered inside <Suspense> (Next 16 Cache
 * Components: session reads can't be part of the static shell).
 */

export type Run = {
  id: string; stage: string; agent: string | null; status: string; started_at: string;
  ended_at: string | null; items_in: number; items_out: number; tokens: number; error: string | null;
};

export async function loadLive() {
  const { supabase } = await requireUser();
  const since = new Date(Date.now() - 24 * 3600 * 1000).toISOString();
  const [runs, budget] = await Promise.all([
    supabase.from("runs").select("*").order("started_at", { ascending: false }).limit(30),
    supabase.from("budget_ledger").select("total_tokens").gte("at", since),
  ]);
  const tokens24h = (budget.data ?? []).reduce((s, b) => s + Number(b.total_tokens), 0);
  return { runs: (runs.data ?? []) as Run[], tokens24h, error: runs.error?.message ?? budget.error?.message };
}

export type OpportunityRow = {
  track: string; type: string; title: string; org: string | null; status: string; priority: number | null;
  deadline: string | null; location: string | null; url: string; fit: number | null; value: number | null;
  recommendation: string | null;
};

export async function loadOpportunities() {
  const { supabase } = await requireUser();
  const { data, error } = await supabase
    .from("opportunity_sheet")
    .select("track,type,title,org,status,priority,deadline,location,url,fit,value,recommendation")
    .not("recommendation", "is", null)
    .order("priority", { ascending: false, nullsFirst: false })
    .limit(200);
  return { rows: (data ?? []) as OpportunityRow[], error: error?.message };
}

export async function loadLatestDigest() {
  const { supabase } = await requireUser();
  const { data, error } = await supabase
    .from("digests").select("for_date,content_md").order("for_date", { ascending: false }).limit(1);
  return { digest: data?.[0] as { for_date: string; content_md: string } | undefined, error: error?.message };
}
