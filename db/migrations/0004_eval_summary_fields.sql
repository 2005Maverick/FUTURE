-- Evaluator output fields the digest/dashboard need (S02.05b).
alter table public.evaluations add column if not exists one_line text;
alter table public.evaluations add column if not exists details jsonb not null default '{}';
