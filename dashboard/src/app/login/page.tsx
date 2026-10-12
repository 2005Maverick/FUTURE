"use client";
import { useActionState } from "react";
import { sendMagicLink, type LoginState } from "./actions";

export default function LoginPage() {
  const [state, action, pending] = useActionState<LoginState, FormData>(sendMagicLink, { sent: false });
  return (
    <main className="mx-auto mt-24 max-w-sm px-4">
      <h1 className="mb-1 text-2xl font-semibold">FUTURE</h1>
      <p className="mb-6 text-sm text-neutral-500">Private dashboard. Sign in with a one-time email link.</p>
      {state.sent ? (
        <p className="rounded-md border border-neutral-300 p-3 text-sm dark:border-neutral-700">
          If that address is allowed, a sign-in link is on its way. Check your inbox.
        </p>
      ) : (
        <form action={action} className="space-y-3">
          <input
            name="email"
            type="email"
            required
            placeholder="you@example.com"
            className="w-full rounded-md border border-neutral-300 bg-transparent px-3 py-2 dark:border-neutral-700"
          />
          <button
            disabled={pending}
            className="w-full rounded-md bg-neutral-900 px-3 py-2 text-white disabled:opacity-50 dark:bg-white dark:text-neutral-900"
          >
            {pending ? "Sending…" : "Send sign-in link"}
          </button>
          {state.error && <p className="text-sm text-red-600">{state.error}</p>}
        </form>
      )}
    </main>
  );
}
