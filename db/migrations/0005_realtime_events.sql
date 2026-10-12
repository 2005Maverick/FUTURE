-- Live agent view (S02.06): stream new events/runs to the signed-in owner via Supabase Realtime.
-- Realtime postgres_changes respects RLS, so only the owner receives rows.
alter publication supabase_realtime add table public.events, public.runs;
