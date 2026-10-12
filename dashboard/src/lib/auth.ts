import "server-only";
import { redirect } from "next/navigation";
import { supabaseServer } from "@/lib/supabase/server";

/**
 * Data-access-layer guard: every page calls this. proxy.ts is only an optimistic
 * redirect (Next 16 docs); the authoritative checks are getUser() here and RLS
 * (owner-only policies) in the database.
 */
export async function requireUser() {
  const supabase = await supabaseServer();
  const { data, error } = await supabase.auth.getUser();
  if (error || !data.user) redirect("/login");
  return { supabase, user: data.user };
}
