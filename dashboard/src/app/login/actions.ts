"use server";
import { headers } from "next/headers";
import { supabaseServer } from "@/lib/supabase/server";

export type LoginState = { sent: boolean; error?: string };

/**
 * Sends a magic link ONLY to the owner's address (OWNER_EMAIL, server-side env).
 * Any other address gets the same "check your email" reply and no email is sent,
 * so the page reveals nothing and can't be used to spam strangers.
 */
export async function sendMagicLink(_: LoginState, form: FormData): Promise<LoginState> {
  const email = String(form.get("email") ?? "").trim().toLowerCase();
  const owner = (process.env.OWNER_EMAIL ?? "").trim().toLowerCase();
  if (!email || !email.includes("@")) return { sent: false, error: "Enter an email address." };
  if (!owner || email !== owner) return { sent: true };
  const origin = (await headers()).get("origin") ?? process.env.NEXT_PUBLIC_SITE_URL ?? "";
  const supabase = await supabaseServer();
  const { error } = await supabase.auth.signInWithOtp({
    email,
    options: { emailRedirectTo: `${origin}/auth/callback` },
  });
  if (error) return { sent: false, error: "Could not send the link. Try again in a minute." };
  return { sent: true };
}
