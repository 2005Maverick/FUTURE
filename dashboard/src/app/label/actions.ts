"use server";
import { revalidatePath } from "next/cache";
import { requireUser } from "@/lib/auth";

export type LabelResult = { ok: boolean; error?: string };

/** Save one blind label (RLS: only the owner can write labels). */
export async function saveLabel(_: LabelResult, form: FormData): Promise<LabelResult> {
  const { supabase } = await requireUser();
  const targetId = String(form.get("target_id") ?? "");
  const worth = form.get("worth_applying");
  const rating = Number(form.get("rating"));
  const reason = String(form.get("reason") ?? "").slice(0, 500);
  if (!targetId || (worth !== "yes" && worth !== "no") || !(rating >= 1 && rating <= 5)) {
    return { ok: false, error: "Pick yes/no and a 1–5 rating." };
  }
  const { error } = await supabase.from("labels").upsert(
    { target_type: "opportunity", target_id: targetId, worth_applying: worth === "yes", rating, reason },
    { onConflict: "target_type,target_id" },
  );
  if (error) return { ok: false, error: "Could not save. Try again." };
  revalidatePath("/label");
  return { ok: true };
}
