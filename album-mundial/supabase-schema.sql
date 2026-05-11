-- ============================================================================
-- Álbum Mundial — schema "álbum compartido entre miembros"
-- Aplica este archivo completo en: Supabase Dashboard > SQL Editor > New query.
-- Es idempotente: lo puedes correr varias veces sin romper nada.
--
-- Modelo:
--   users (1 por auth user, incluidos los anónimos)
--     ↓ owner_id
--   albums (uno o varios por dueño, con invite_code único)
--     ↓ album_id            ← stickers viven aquí (compartidos por miembros)
--   album_members (1 fila por user que pertenece a un álbum)
--   friendships (entre álbumes, no entre miembros — para intercambios externos)
-- ============================================================================

-- ---------- USERS ---------------------------------------------------------
create table if not exists public.users (
  id         uuid primary key references auth.users(id) on delete cascade,
  created_at timestamptz not null default now()
);

-- ---------- ALBUMS --------------------------------------------------------
create table if not exists public.albums (
  id          uuid primary key default gen_random_uuid(),
  owner_id    uuid not null references public.users(id) on delete cascade,
  name        text not null default 'Nuestro álbum',
  invite_code text not null unique,
  created_at  timestamptz not null default now()
);

create index if not exists albums_owner_idx  on public.albums(owner_id);
create index if not exists albums_invite_idx on public.albums(invite_code);

-- ---------- ALBUM_MEMBERS -------------------------------------------------
create table if not exists public.album_members (
  album_id    uuid not null references public.albums(id) on delete cascade,
  user_id     uuid not null references public.users(id) on delete cascade,
  member_name text not null default 'Miembro',
  joined_at   timestamptz not null default now(),
  primary key (album_id, user_id)
);

create index if not exists album_members_user_idx on public.album_members(user_id);

-- ---------- STICKERS ------------------------------------------------------
create table if not exists public.stickers (
  album_id   uuid     not null references public.albums(id) on delete cascade,
  code       text     not null check (char_length(code) between 1 and 16),
  status     smallint not null check (status in (1, 2)), -- 1=pegada, 2=repetida
  count      smallint not null default 0,
  updated_at timestamptz not null default now(),
  primary key (album_id, code)
);

create index if not exists stickers_album_idx on public.stickers(album_id);

-- ---------- FRIENDSHIPS ENTRE ÁLBUMES ------------------------------------
create table if not exists public.friendships (
  album_a    uuid not null references public.albums(id) on delete cascade,
  album_b    uuid not null references public.albums(id) on delete cascade,
  created_at timestamptz not null default now(),
  primary key (album_a, album_b),
  check (album_a < album_b)
);

create index if not exists friendships_a_idx on public.friendships(album_a);
create index if not exists friendships_b_idx on public.friendships(album_b);

-- ---------- REALTIME ------------------------------------------------------
do $$
begin
  if not exists (select 1 from pg_publication_tables where pubname='supabase_realtime' and schemaname='public' and tablename='albums') then
    alter publication supabase_realtime add table public.albums;
  end if;
  if not exists (select 1 from pg_publication_tables where pubname='supabase_realtime' and schemaname='public' and tablename='album_members') then
    alter publication supabase_realtime add table public.album_members;
  end if;
  if not exists (select 1 from pg_publication_tables where pubname='supabase_realtime' and schemaname='public' and tablename='stickers') then
    alter publication supabase_realtime add table public.stickers;
  end if;
  if not exists (select 1 from pg_publication_tables where pubname='supabase_realtime' and schemaname='public' and tablename='friendships') then
    alter publication supabase_realtime add table public.friendships;
  end if;
end $$;

-- ============================================================================
--                              RLS POLICIES
-- ============================================================================

alter table public.users         enable row level security;
alter table public.albums        enable row level security;
alter table public.album_members enable row level security;
alter table public.stickers      enable row level security;
alter table public.friendships   enable row level security;

-- users: cada uno gestiona su propia fila
drop policy if exists "users readable by authenticated" on public.users;
drop policy if exists "users insert own row"            on public.users;
drop policy if exists "users update own row"            on public.users;

create policy "users readable by authenticated"
  on public.users for select to authenticated using (true);
create policy "users insert own row"
  on public.users for insert to authenticated with check (auth.uid() = id);
create policy "users update own row"
  on public.users for update to authenticated using (auth.uid() = id) with check (auth.uid() = id);

-- albums: cualquier autenticado lee (para buscar por código); solo el dueño edita
drop policy if exists "albums readable by authenticated" on public.albums;
drop policy if exists "albums insert by owner"           on public.albums;
drop policy if exists "albums update by owner"           on public.albums;
drop policy if exists "albums delete by owner"           on public.albums;

create policy "albums readable by authenticated"
  on public.albums for select to authenticated using (true);
create policy "albums insert by owner"
  on public.albums for insert to authenticated with check (auth.uid() = owner_id);
create policy "albums update by owner"
  on public.albums for update to authenticated using (auth.uid() = owner_id) with check (auth.uid() = owner_id);
create policy "albums delete by owner"
  on public.albums for delete to authenticated using (auth.uid() = owner_id);

-- album_members: lectura libre (autenticado); cada uno gestiona su propia fila;
-- el dueño puede expulsar miembros.
drop policy if exists "members readable by authenticated" on public.album_members;
drop policy if exists "members insert self"               on public.album_members;
drop policy if exists "members update self"               on public.album_members;
drop policy if exists "members delete self or owner"      on public.album_members;

create policy "members readable by authenticated"
  on public.album_members for select to authenticated using (true);
create policy "members insert self"
  on public.album_members for insert to authenticated with check (auth.uid() = user_id);
create policy "members update self"
  on public.album_members for update to authenticated using (auth.uid() = user_id) with check (auth.uid() = user_id);
create policy "members delete self or owner"
  on public.album_members for delete to authenticated using (
    auth.uid() = user_id
    or exists (select 1 from public.albums a where a.id = album_id and a.owner_id = auth.uid())
  );

-- stickers: cualquier autenticado lee (para matches con otros álbumes);
-- solo los miembros del álbum escriben.
drop policy if exists "stickers readable by authenticated" on public.stickers;
drop policy if exists "stickers insert by member"          on public.stickers;
drop policy if exists "stickers update by member"          on public.stickers;
drop policy if exists "stickers delete by member"          on public.stickers;

create policy "stickers readable by authenticated"
  on public.stickers for select to authenticated using (true);
create policy "stickers insert by member"
  on public.stickers for insert to authenticated with check (
    exists (select 1 from public.album_members m where m.album_id = stickers.album_id and m.user_id = auth.uid())
  );
create policy "stickers update by member"
  on public.stickers for update to authenticated
  using (exists (select 1 from public.album_members m where m.album_id = stickers.album_id and m.user_id = auth.uid()))
  with check (exists (select 1 from public.album_members m where m.album_id = stickers.album_id and m.user_id = auth.uid()));
create policy "stickers delete by member"
  on public.stickers for delete to authenticated using (
    exists (select 1 from public.album_members m where m.album_id = stickers.album_id and m.user_id = auth.uid())
  );

-- friendships entre álbumes: solo miembros de alguno de los dos pueden ver/crear
drop policy if exists "friendships readable by member"  on public.friendships;
drop policy if exists "friendships insert by member"    on public.friendships;
drop policy if exists "friendships delete by member"    on public.friendships;

create policy "friendships readable by member"
  on public.friendships for select to authenticated using (
    exists (select 1 from public.album_members m where m.album_id = album_a and m.user_id = auth.uid())
    or exists (select 1 from public.album_members m where m.album_id = album_b and m.user_id = auth.uid())
  );
create policy "friendships insert by member"
  on public.friendships for insert to authenticated with check (
    exists (select 1 from public.album_members m where m.album_id = album_a and m.user_id = auth.uid())
    or exists (select 1 from public.album_members m where m.album_id = album_b and m.user_id = auth.uid())
  );
create policy "friendships delete by member"
  on public.friendships for delete to authenticated using (
    exists (select 1 from public.album_members m where m.album_id = album_a and m.user_id = auth.uid())
    or exists (select 1 from public.album_members m where m.album_id = album_b and m.user_id = auth.uid())
  );

-- ============================================================================
-- IMPORTANTE: Para que Emma y la familia entren sin Google, habilita
-- "Allow anonymous sign-ins" en:
--   Supabase Dashboard → Authentication → Sign In / Providers (Supabase Auth)
-- ============================================================================
