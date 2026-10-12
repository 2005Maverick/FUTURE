-- FUTURE schema v1 (DESIGN §7). Single-user system.
-- Access model:
--   * pipeline (laptop) uses the secret/service key -> bypasses RLS
--   * dashboard uses Pranav's auth session -> allowed only if public.is_owner()
--   * anon -> no policies -> denied everywhere
-- No personal data in this file (public repo). The owner row is inserted out-of-band.

create extension if not exists pgcrypto with schema extensions;

-- ---------- helpers ----------
create table public.app_owner (
  user_id uuid primary key,
  created_at timestamptz not null default now()
);

create or replace function public.is_owner()
returns boolean
language sql stable security definer
set search_path = ''
as $$
  select exists (select 1 from public.app_owner o where o.user_id = (select auth.uid()));
$$;

create or replace function public.touch_updated_at()
returns trigger language plpgsql set search_path = '' as $$
begin
  new.updated_at := now();
  return new;
end;
$$;

-- ---------- sources & raw intake ----------
create table public.sources (
  id uuid primary key default gen_random_uuid(),
  name text not null unique,
  kind text not null check (kind in ('ats','api','rss','page','email','whatsapp','github','search','manual')),
  track text check (track in ('job','research','ms','hackathon','funding','mixed')),
  method text,
  url text,
  config jsonb not null default '{}',
  terms_verdict text not null default 'unknown' check (terms_verdict in ('allowed','alerts_only','forbidden','unknown')),
  enabled boolean not null default true,
  health text not null default 'unknown' check (health in ('ok','degraded','failing','unknown')),
  last_run_at timestamptz,
  yield jsonb not null default '{}',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table public.raw_items (
  id uuid primary key default gen_random_uuid(),
  source_id uuid not null references public.sources(id) on delete cascade,
  external_id text,
  url text,
  fetched_at timestamptz not null default now(),
  content_hash text not null unique,
  payload jsonb not null,
  process_status text not null default 'new' check (process_status in ('new','extracted','skipped','error')),
  processed_at timestamptz,
  error text
);
create index raw_items_status_idx on public.raw_items (process_status, fetched_at);

-- ---------- opportunities ----------
create table public.opportunities (
  id uuid primary key default gen_random_uuid(),
  type text not null check (type in ('job','internship','contract','research_internship','predoc','lab_outreach',
    'ms_program','scholarship','hackathon','competition','grant','accelerator','fellowship','credits','travel_grant')),
  track text not null check (track in ('job','research','ms','hackathon','funding')),
  title text not null,
  org text,
  url text not null,
  canonical_url text,
  dedup_key text not null unique,
  location text,
  remote text not null default 'unknown' check (remote in ('remote','hybrid','onsite','unknown')),
  countries text[] not null default '{}',
  pay_min numeric,
  pay_max numeric,
  pay_currency text,
  pay_period text check (pay_period in ('year','month','hour','total','unknown')),
  deadline date,
  starts_on date,
  eligibility jsonb not null default '{}',
  needs_company boolean,
  details jsonb not null default '{}',
  status text not null default 'found' check (status in ('found','verified','scored','shortlisted','preparing',
    'awaiting_approval','submitted','reply','interview','offer','rejected','no_response','skipped','expired')),
  skip_reason text,
  priority numeric,
  first_seen_at timestamptz not null default now(),
  last_seen_at timestamptz not null default now(),
  live_checked_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index opportunities_status_priority_idx on public.opportunities (status, priority desc);
create index opportunities_deadline_idx on public.opportunities (deadline) where deadline is not null;
create index opportunities_track_idx on public.opportunities (track, status);

create table public.opportunity_sources (
  opportunity_id uuid not null references public.opportunities(id) on delete cascade,
  raw_item_id uuid not null references public.raw_items(id) on delete cascade,
  primary key (opportunity_id, raw_item_id)
);

-- ---------- runs, events, budget ----------
create table public.runs (
  id uuid primary key default gen_random_uuid(),
  stage text not null,
  agent text,
  started_at timestamptz not null default now(),
  ended_at timestamptz,
  status text not null default 'running' check (status in ('running','ok','error','skipped','budget_exhausted')),
  items_in integer not null default 0,
  items_out integer not null default 0,
  tokens integer not null default 0,
  cost_usd numeric not null default 0,
  error text,
  meta jsonb not null default '{}'
);
create index runs_started_idx on public.runs (started_at desc);

create table public.events (
  id bigint generated always as identity primary key,
  run_id uuid references public.runs(id) on delete cascade,
  at timestamptz not null default now(),
  level text not null default 'info' check (level in ('debug','info','warn','error')),
  kind text not null,
  message text,
  data jsonb not null default '{}'
);
create index events_run_idx on public.events (run_id, at);
create index events_at_idx on public.events (at desc);

create table public.budget_ledger (
  id bigint generated always as identity primary key,
  at timestamptz not null default now(),
  run_id uuid references public.runs(id) on delete set null,
  purpose text not null,
  model text not null,
  input_tokens integer not null default 0,
  output_tokens integer not null default 0,
  cache_create_tokens integer not null default 0,
  cache_read_tokens integer not null default 0,
  total_tokens integer not null default 0,
  cost_usd numeric not null default 0
);
create index budget_ledger_at_idx on public.budget_ledger (at desc);

-- ---------- judgement ----------
create table public.evaluations (
  id uuid primary key default gen_random_uuid(),
  opportunity_id uuid not null references public.opportunities(id) on delete cascade,
  rubric text not null,
  rubric_version text not null,
  fit smallint check (fit between 1 and 5),
  value smallint check (value between 1 and 5),
  eligibility text check (eligibility in ('pass','fail','unclear')),
  legitimacy text check (legitimacy in ('ok','suspect')),
  evidence jsonb not null default '[]',
  gaps jsonb not null default '[]',
  recommendation text,
  model text,
  tokens integer,
  run_id uuid references public.runs(id) on delete set null,
  created_at timestamptz not null default now()
);
create index evaluations_opp_idx on public.evaluations (opportunity_id, created_at desc);

create table public.labels (
  id uuid primary key default gen_random_uuid(),
  target_type text not null check (target_type in ('opportunity','document')),
  target_id uuid not null,
  rating smallint check (rating between 1 and 5),
  worth_applying boolean,
  reason text,
  created_at timestamptz not null default now(),
  unique (target_type, target_id)
);

-- ---------- people ----------
create table public.contacts (
  id uuid primary key default gen_random_uuid(),
  name text not null,
  org text,
  title text,
  relation text check (relation in ('connection','coauthor','colleague','recruiter','professor','mentor','other')),
  email text,
  profile_url text,
  source text,
  notes text,
  created_at timestamptz not null default now()
);
create index contacts_org_idx on public.contacts (lower(org));

create table public.referral_matches (
  id uuid primary key default gen_random_uuid(),
  opportunity_id uuid not null references public.opportunities(id) on delete cascade,
  contact_id uuid not null references public.contacts(id) on delete cascade,
  path text,
  strength smallint check (strength between 1 and 5),
  created_at timestamptz not null default now(),
  unique (opportunity_id, contact_id)
);

-- ---------- preparation & action ----------
create table public.documents (
  id uuid primary key default gen_random_uuid(),
  opportunity_id uuid references public.opportunities(id) on delete cascade,
  kind text not null check (kind in ('cv','cover_letter','sop','professor_email','referral_ask','grant_answers',
    'form_answers','follow_up','other')),
  version integer not null default 1,
  content text not null,
  claim_map jsonb not null default '[]',
  critic_verdict text not null default 'pending' check (critic_verdict in ('pending','pass','revise','block')),
  critic_notes jsonb not null default '[]',
  model text,
  tokens integer,
  created_at timestamptz not null default now(),
  unique (opportunity_id, kind, version)
);

create table public.approvals (
  id uuid primary key default gen_random_uuid(),
  opportunity_id uuid references public.opportunities(id) on delete cascade,
  document_id uuid references public.documents(id) on delete cascade,
  action text not null check (action in ('prepare','submit','send','follow_up')),
  payload_hash text not null,
  status text not null default 'pending' check (status in ('pending','approved','rejected','expired')),
  requested_at timestamptz not null default now(),
  decided_at timestamptz,
  channel text,
  note text
);
create index approvals_status_idx on public.approvals (status, requested_at);

create table public.applications (
  id uuid primary key default gen_random_uuid(),
  opportunity_id uuid not null references public.opportunities(id) on delete cascade,
  approval_id uuid references public.approvals(id) on delete set null,
  submitted_at timestamptz not null default now(),
  channel text,
  evidence jsonb not null default '{}',
  follow_up_on date,
  outcome text not null default 'none' check (outcome in ('none','reply','interview','offer','rejected','no_response','withdrawn')),
  outcome_at timestamptz,
  notes text
);

create table public.digests (
  id uuid primary key default gen_random_uuid(),
  for_date date not null unique,
  content_md text not null,
  created_at timestamptz not null default now()
);

create table public.settings (
  key text primary key,
  value jsonb not null,
  updated_at timestamptz not null default now()
);

-- ---------- updated_at triggers ----------
create trigger sources_touch before update on public.sources for each row execute function public.touch_updated_at();
create trigger opportunities_touch before update on public.opportunities for each row execute function public.touch_updated_at();
create trigger settings_touch before update on public.settings for each row execute function public.touch_updated_at();

-- ---------- RLS: owner-only for every table ----------
do $$
declare t text;
begin
  foreach t in array array['app_owner','sources','raw_items','opportunities','opportunity_sources','runs','events',
    'budget_ledger','evaluations','labels','contacts','referral_matches','documents','approvals','applications',
    'digests','settings']
  loop
    execute format('alter table public.%I enable row level security', t);
    execute format('create policy owner_all on public.%I for all to authenticated using ((select public.is_owner())) with check ((select public.is_owner()))', t);
  end loop;
end $$;

revoke execute on function public.is_owner() from anon;

-- ---------- sheet mirror view (read through owner/service only; RPC for the Sheet comes in S02.05) ----------
create view public.opportunity_sheet with (security_invoker = true) as
select o.track, o.type, o.title, o.org, o.status, o.priority, o.deadline, o.remote, o.location,
       o.pay_min, o.pay_max, o.pay_currency, o.pay_period, o.url,
       e.fit, e.value, e.recommendation, o.first_seen_at, o.updated_at
from public.opportunities o
left join lateral (
  select fit, value, recommendation from public.evaluations ev
  where ev.opportunity_id = o.id order by ev.created_at desc limit 1
) e on true
where o.status not in ('skipped','expired');
