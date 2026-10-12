-- Evaluation cache key: re-evaluate an opportunity only when the text the
-- Evaluator saw (title/location/description) changed. (S02.05b)
alter table public.evaluations add column if not exists input_hash text;
create index if not exists evaluations_cache_idx
  on public.evaluations (opportunity_id, rubric_version, input_hash);
