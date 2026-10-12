import { Suspense } from "react";
import { loadLatestDigest } from "@/lib/data";

export default function DigestPage() {
  return (
    <div>
      <h1 className="mb-4 text-xl font-semibold">Digest</h1>
      <Suspense fallback={<p className="text-sm text-neutral-500">Loading…</p>}>
        <Latest />
      </Suspense>
    </div>
  );
}

async function Latest() {
  const { digest, error } = await loadLatestDigest();
  if (error) return <p className="text-sm text-red-600">Could not load: {error}</p>;
  if (!digest) return <p className="text-sm text-neutral-500">No digest yet.</p>;
  return (
    <>
      <p className="mb-3 text-sm text-neutral-500">{digest.for_date}</p>
      <pre className="whitespace-pre-wrap font-sans text-sm leading-relaxed">{digest.content_md}</pre>
    </>
  );
}
