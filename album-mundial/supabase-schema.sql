-- ============================================================================
-- Álbum Mundial — schema + Row-Level Security para Supabase
-- Aplica este archivo completo en: Supabase Dashboard > SQL Editor > New query.
-- Es idempotente: lo puedes correr varias veces sin romper nada.
-- ============================================================================

-- ---------- TABLA users ---------------------------------------------------
create table if not exists public.users (
  id           uuid primary key references auth.users(id) on delete cascade,
  display_name text         not null default 'Sin nombre',
  photo_url    text         not null default '',
  invite_code  text         not null unique,
  created_at   timestamptz  not null default now()
);

create index if not exists users_invite_code_idx on public.users(invite_code);

-- ---------- TABLA stickers ------------------------------------------------
create table if not exists public.stickers (
  user_id  uuid     not null references public.users(id) on delete cascade,
  n        int      not null check (n between 1 and 2000),
  status   smallint not null check (status in (1, 2)), -- 1=pegada, 2=repetida
  count    smallint not null default 0,
  updated_at timestamptz not null default now(),
  primary key (user_id, n)
);

create index if not exists stickers_user_idx   on public.stickers(user_id);
create index if not exists stickers_status_idx on public.stickers(user_id, status);

-- ---------- TABLA friendships ---------------------------------------------
-- user_a < user_b siempre, para evitar pares duplicados.
create table if not exists public.friendships (
  user_a     uuid not null references public.users(id) on delete cascade,
  user_b     uuid not null references public.users(id) on delete cascade,
  created_at timestamptz not null default now(),
  primary key (user_a, user_b),
  check (user_a < user_b)
);

create index if not exists friendships_a_idx on public.friendships(user_a);
create index if not exists friendships_b_idx on public.friendships(user_b);

-- ---------- HABILITAR REALTIME -------------------------------------------
-- (Necesario para que las suscripciones del cliente reciban cambios.)
do $$
begin
  if not exists (
    select 1 from pg_publication_tables
    where pubname = 'supabase_realtime' and schemaname = 'public' and tablename = 'users'
  ) then
    alter publication supabase_realtime add table public.users;
  end if;
  if not exists (
    select 1 from pg_publication_tables
    where pubname = 'supabase_realtime' and schemaname = 'public' and tablename = 'stickers'
  ) then
    alter publication supabase_realtime add table public.stickers;
  end if;
  if not exists (
    select 1 from pg_publication_tables
    where pubname = 'supabase_realtime' and schemaname = 'public' and tablename = 'friendships'
  ) then
    alter publication supabase_realtime add table public.friendships;
  end if;
end $$;

-- ============================================================================
--                              RLS POLICIES
-- ============================================================================

alter table public.users       enable row level security;
alter table public.stickers    enable row level security;
alter table public.friendships enable row level security;

-- ---------- users ---------------------------------------------------------
drop policy if exists "users readable by authenticated"  on public.users;
drop policy if exists "users insert own row"             on public.users;
drop policy if exists "users update own row"             on public.users;

create policy "users readable by authenticated"
  on public.users for select
  to authenticated
  using (true);

create policy "users insert own row"
  on public.users for insert
  to authenticated
  with check (auth.uid() = id);

create policy "users update own row"
  on public.users for update
  to authenticated
  using (auth.uid() = id)
  with check (auth.uid() = id);

-- ---------- stickers ------------------------------------------------------
drop policy if exists "stickers readable by authenticated" on public.stickers;
drop policy if exists "stickers insert own"                on public.stickers;
drop policy if exists "stickers update own"                on public.stickers;
drop policy if exists "stickers delete own"                on public.stickers;

create policy "stickers readable by authenticated"
  on public.stickers for select
  to authenticated
  using (true);

create policy "stickers insert own"
  on public.stickers for insert
  to authenticated
  with check (auth.uid() = user_id);

create policy "stickers update own"
  on public.stickers for update
  to authenticated
  using (auth.uid() = user_id)
  with check (auth.uid() = user_id);

create policy "stickers delete own"
  on public.stickers for delete
  to authenticated
  using (auth.uid() = user_id);

-- ---------- friendships ---------------------------------------------------
drop policy if exists "friendships readable by participants" on public.friendships;
drop policy if exists "friendships insertable by participants" on public.friendships;
drop policy if exists "friendships deletable by participants" on public.friendships;

create policy "friendships readable by participants"
  on public.friendships for select
  to authenticated
  using (auth.uid() = user_a or auth.uid() = user_b);

create policy "friendships insertable by participants"
  on public.friendships for insert
  to authenticated
  with check (auth.uid() = user_a or auth.uid() = user_b);

create policy "friendships deletable by participants"
  on public.friendships for delete
  to authenticated
  using (auth.uid() = user_a or auth.uid() = user_b);

-- ============================================================================
-- Listo. Próximo paso: en Authentication > Providers habilita Google y agrega
-- tu dominio (ej. https://<usuario>.github.io) en URL Configuration.
-- ============================================================================
