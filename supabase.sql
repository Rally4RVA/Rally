-- Rally: shared "Interested" counts.
-- Paste this whole file into Supabase > SQL Editor > New query, then click Run.

-- One row per (show, device). No names, no emails, nothing personal.
create table if not exists public.interest (
  show_id    text not null,
  device_id  text not null,
  created_at timestamptz not null default now(),
  primary key (show_id, device_id)
);

-- Lock the table: the website can't read or write it directly.
alter table public.interest enable row level security;

-- The site can only do two things, through these two functions.
create or replace function public.set_interest(p_show text, p_device text, p_on boolean)
returns void
language plpgsql
security definer
set search_path = public
as $$
begin
  if p_show is null or p_device is null
     or length(p_show) = 0 or length(p_show) > 200
     or length(p_device) < 8 or length(p_device) > 80 then
    raise exception 'bad input';
  end if;
  if p_on then
    insert into public.interest (show_id, device_id) values (p_show, p_device)
    on conflict do nothing;
  else
    delete from public.interest where show_id = p_show and device_id = p_device;
  end if;
end;
$$;

create or replace function public.interest_counts()
returns table (show_id text, n bigint)
language sql
security definer
set search_path = public
stable
as $$
  select i.show_id, count(*)::bigint
  from public.interest i
  group by i.show_id;
$$;

revoke all on function public.set_interest(text, text, boolean) from public;
revoke all on function public.interest_counts() from public;
grant execute on function public.set_interest(text, text, boolean) to anon;
grant execute on function public.interest_counts() to anon;
