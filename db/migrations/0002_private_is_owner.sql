-- Fix advisor lint 0028/0029: is_owner() (SECURITY DEFINER) was callable via /rest/v1/rpc.
-- Move it to a schema PostgREST does not expose; keep it executable by `authenticated`
-- (policies evaluate as the caller) but not by anon/public.

create schema if not exists private;
revoke all on schema private from public, anon;
grant usage on schema private to authenticated, service_role;

create or replace function private.is_owner()
returns boolean
language sql stable security definer
set search_path = ''
as $$
  select exists (select 1 from public.app_owner o where o.user_id = (select auth.uid()));
$$;
revoke all on function private.is_owner() from public, anon;
grant execute on function private.is_owner() to authenticated, service_role;

do $$
declare t text;
begin
  foreach t in array array['app_owner','sources','raw_items','opportunities','opportunity_sources','runs','events',
    'budget_ledger','evaluations','labels','contacts','referral_matches','documents','approvals','applications',
    'digests','settings']
  loop
    execute format('drop policy if exists owner_all on public.%I', t);
    execute format('create policy owner_all on public.%I for all to authenticated using ((select private.is_owner())) with check ((select private.is_owner()))', t);
  end loop;
end $$;

drop function public.is_owner();
