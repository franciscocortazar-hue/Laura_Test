// Capa de datos: Supabase si está configurado; si no, localStorage (modo demo).
// Modelo: "álbum compartido entre miembros". 1 álbum tiene N miembros,
// todos editan el mismo conjunto de stickers.

import { supabaseConfig, isSupabaseConfigured } from "./supabase-config.js";
import { TOTAL_STICKERS } from "./album-structure.js";

const LS_KEY = "album-mundial:v2";
const DEMO_SESSION_KEY = "album-mundial:session";

function makeInviteCode() {
  const ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789";
  let s = "";
  for (let i = 0; i < 6; i++) s += ALPHABET[Math.floor(Math.random() * ALPHABET.length)];
  return s;
}

// ============================================================================
//  Backend: LOCAL (demo / sin login) — 1 álbum, 1 miembro (tú).
// ============================================================================
class LocalBackend {
  constructor() {
    this.data = this._read();
  }
  _read() {
    try {
      const raw = localStorage.getItem(LS_KEY);
      if (!raw) return { albums: {}, members: [], friendships: [] };
      return JSON.parse(raw);
    } catch {
      return { albums: {}, members: [], friendships: [] };
    }
  }
  _write() { localStorage.setItem(LS_KEY, JSON.stringify(this.data)); }

  getSessionUid()    { return localStorage.getItem(DEMO_SESSION_KEY); }
  setSessionUid(uid) { localStorage.setItem(DEMO_SESSION_KEY, uid); }
  clearSession()     { localStorage.removeItem(DEMO_SESSION_KEY); }

  async loginWithGoogle() { throw new Error("Login con Google requiere Supabase."); }
  async loginAnonymously() { throw new Error("Login anónimo requiere Supabase."); }
  async logout() { this.clearSession(); }

  async ensureUser() { /* nada */ }

  async ensureDefaultAlbum(uid, displayName) {
    let album = Object.values(this.data.albums).find(a => a.owner_id === uid);
    if (!album) {
      const id = "alb-" + Math.random().toString(36).slice(2, 10);
      album = { id, owner_id: uid, name: displayName || "Mi álbum", invite_code: makeInviteCode(), stickers: {}, created_at: Date.now() };
      this.data.albums[id] = album;
      this.data.members.push({ album_id: id, user_id: uid, member_name: displayName || "Yo", joined_at: Date.now() });
      this._write();
    }
    return album;
  }

  async listAlbumsForUser(uid) {
    const ids = new Set(this.data.members.filter(m => m.user_id === uid).map(m => m.album_id));
    return Object.values(this.data.albums).filter(a => ids.has(a.id));
  }

  async getAlbum(albumId) { return this.data.albums[albumId] || null; }

  async findAlbumByCode(code) {
    code = (code || "").toUpperCase();
    return Object.values(this.data.albums).find(a => a.invite_code === code) || null;
  }

  async joinAlbumByCode(uid, code, memberName) {
    const album = await this.findAlbumByCode(code);
    if (!album) return { ok: false, reason: "not_found" };
    const exists = this.data.members.find(m => m.album_id === album.id && m.user_id === uid);
    if (!exists) {
      this.data.members.push({ album_id: album.id, user_id: uid, member_name: memberName || "Miembro", joined_at: Date.now() });
      this._write();
    }
    return { ok: true, album };
  }

  async listMembers(albumId) {
    return this.data.members.filter(m => m.album_id === albumId);
  }

  async updateMemberName(albumId, uid, name) {
    const m = this.data.members.find(x => x.album_id === albumId && x.user_id === uid);
    if (m) { m.member_name = name; this._write(); }
  }

  async setSticker(albumId, code, status, count) {
    const a = this.data.albums[albumId];
    if (!a) return;
    if (status === 0) delete a.stickers[code];
    else a.stickers[code] = { s: status, c: count };
    this._write();
  }

  async getStickers(albumId) {
    const a = this.data.albums[albumId];
    return a ? { ...(a.stickers || {}) } : {};
  }

  async addFriendship(a, b) {
    if (a === b) return false;
    const [u1, u2] = [a, b].sort();
    const exists = this.data.friendships.find(f => f[0] === u1 && f[1] === u2);
    if (exists) return false;
    this.data.friendships.push([u1, u2, Date.now()]);
    this._write();
    return true;
  }

  async listFriendAlbums(albumId) {
    const ids = this.data.friendships
      .filter(f => f[0] === albumId || f[1] === albumId)
      .map(f => f[0] === albumId ? f[1] : f[0]);
    return ids.map(id => this.data.albums[id]).filter(Boolean);
  }

  onAuthChanged(cb) {
    const uid = this.getSessionUid();
    cb(uid ? { uid } : null);
    return () => {};
  }
  onAlbumChange(albumId, cb)   { cb(this.data.albums[albumId] || null); return () => {}; }
  onMembersChange(albumId, cb) { cb(this.data.members.filter(m => m.album_id === albumId)); return () => {}; }
  onFriendsChange(albumId, cb) { (async () => cb(await this.listFriendAlbums(albumId)))(); return () => {}; }
}

// ============================================================================
//  Backend: SUPABASE
// ============================================================================
class SupabaseBackend {
  constructor() {
    this.client = null;
    this._channels = [];
  }

  async init() {
    const { createClient } = await import("https://esm.sh/@supabase/supabase-js@2.45.4");
    this.client = createClient(supabaseConfig.url, supabaseConfig.anonKey, {
      auth: { persistSession: true, autoRefreshToken: true, detectSessionInUrl: true },
    });
  }

  async loginWithGoogle() {
    const { error } = await this.client.auth.signInWithOAuth({
      provider: "google",
      options: { redirectTo: location.origin + location.pathname.replace(/index\.html$/, "") + "album.html" },
    });
    if (error) throw error;
    return null;
  }

  async loginAnonymously() {
    const { data, error } = await this.client.auth.signInAnonymously();
    if (error) throw error;
    return data.user;
  }

  async logout() { await this.client.auth.signOut(); }

  // Garantiza la fila en public.users (FK target para albums y album_members).
  async ensureUser(uid) {
    const { error } = await this.client
      .from("users")
      .upsert({ id: uid }, { onConflict: "id" });
    if (error) throw error;
  }

  async _generateUniqueInviteCode() {
    for (let i = 0; i < 8; i++) {
      const code = makeInviteCode();
      const { data, error } = await this.client
        .from("albums").select("id").eq("invite_code", code).maybeSingle();
      if (error) throw error;
      if (!data) return code;
    }
    return makeInviteCode();
  }

  async ensureDefaultAlbum(uid, displayName) {
    // ¿Ya posee uno?
    const { data: existing, error: e1 } = await this.client
      .from("albums").select("*").eq("owner_id", uid).limit(1).maybeSingle();
    if (e1) throw e1;
    if (existing) {
      // Asegurar que sea miembro de su propio álbum.
      await this.client.from("album_members")
        .upsert({ album_id: existing.id, user_id: uid, member_name: displayName || "Yo" },
                { onConflict: "album_id,user_id", ignoreDuplicates: true });
      return existing;
    }
    const code = await this._generateUniqueInviteCode();
    const { data, error } = await this.client.from("albums")
      .insert({ owner_id: uid, name: displayName ? `Álbum de ${displayName}` : "Mi álbum", invite_code: code })
      .select().single();
    if (error) throw error;
    await this.client.from("album_members")
      .insert({ album_id: data.id, user_id: uid, member_name: displayName || "Yo" });
    return data;
  }

  async listAlbumsForUser(uid) {
    const { data, error } = await this.client
      .from("album_members")
      .select("album:albums(*)")
      .eq("user_id", uid);
    if (error) throw error;
    return (data || []).map(r => r.album).filter(Boolean);
  }

  async getAlbum(albumId) {
    const { data, error } = await this.client.from("albums").select("*").eq("id", albumId).maybeSingle();
    if (error) throw error;
    return data;
  }

  async findAlbumByCode(code) {
    code = (code || "").toUpperCase();
    const { data, error } = await this.client.from("albums").select("*").eq("invite_code", code).maybeSingle();
    if (error) throw error;
    return data;
  }

  async joinAlbumByCode(uid, code, memberName) {
    const album = await this.findAlbumByCode(code);
    if (!album) return { ok: false, reason: "not_found" };
    const { error } = await this.client.from("album_members")
      .upsert({ album_id: album.id, user_id: uid, member_name: memberName || "Miembro" },
              { onConflict: "album_id,user_id" });
    if (error) throw error;
    return { ok: true, album };
  }

  async listMembers(albumId) {
    const { data, error } = await this.client.from("album_members")
      .select("album_id, user_id, member_name, joined_at")
      .eq("album_id", albumId)
      .order("joined_at", { ascending: true });
    if (error) throw error;
    return data || [];
  }

  async updateMemberName(albumId, uid, name) {
    const { error } = await this.client.from("album_members")
      .update({ member_name: name }).eq("album_id", albumId).eq("user_id", uid);
    if (error) throw error;
  }

  async getStickers(albumId) {
    const { data, error } = await this.client.from("stickers")
      .select("code, status, count").eq("album_id", albumId);
    if (error) throw error;
    const out = {};
    for (const r of (data || [])) out[r.code] = { s: r.status, c: r.count || 0 };
    return out;
  }

  async setSticker(albumId, code, status, count) {
    if (status === 0) {
      const { error } = await this.client.from("stickers").delete()
        .eq("album_id", albumId).eq("code", code);
      if (error) throw error;
    } else {
      const { error } = await this.client.from("stickers").upsert(
        { album_id: albumId, code, status, count: count || 0 },
        { onConflict: "album_id,code" });
      if (error) throw error;
    }
  }

  async addFriendship(albumA, albumB) {
    if (albumA === albumB) return false;
    const [a, b] = [albumA, albumB].sort();
    const { error } = await this.client.from("friendships").insert({ album_a: a, album_b: b });
    if (error) {
      if (error.code === "23505") return false;
      throw error;
    }
    return true;
  }

  async _listFriendAlbumIds(albumId) {
    const { data, error } = await this.client.from("friendships")
      .select("album_a, album_b")
      .or(`album_a.eq.${albumId},album_b.eq.${albumId}`);
    if (error) throw error;
    return (data || []).map(r => r.album_a === albumId ? r.album_b : r.album_a);
  }

  async listFriendAlbums(albumId) {
    const ids = await this._listFriendAlbumIds(albumId);
    if (!ids.length) return [];
    const { data: albums, error: e1 } = await this.client.from("albums").select("*").in("id", ids);
    if (e1) throw e1;
    const { data: stickers, error: e2 } = await this.client.from("stickers")
      .select("album_id, code, status, count").in("album_id", ids);
    if (e2) throw e2;
    const byAlbum = {};
    for (const s of (stickers || [])) {
      (byAlbum[s.album_id] ||= {})[s.code] = { s: s.status, c: s.count || 0 };
    }
    return (albums || []).map(a => ({ ...a, stickers: byAlbum[a.id] || {} }));
  }

  // -------- Subscripciones realtime ----------
  onAlbumChange(albumId, cb) {
    let cancelled = false;
    const reload = async () => {
      if (cancelled) return;
      try {
        const album = await this.getAlbum(albumId);
        if (!album) { cb(null); return; }
        album.stickers = await this.getStickers(albumId);
        cb(album);
      } catch (err) { console.error("onAlbumChange reload error", err); }
    };
    reload();
    const ch = this.client
      .channel("album:" + albumId)
      .on("postgres_changes", { event: "*", schema: "public", table: "stickers", filter: `album_id=eq.${albumId}` }, reload)
      .on("postgres_changes", { event: "*", schema: "public", table: "albums",   filter: `id=eq.${albumId}` }, reload)
      .subscribe();
    this._channels.push(ch);
    return () => { cancelled = true; this.client.removeChannel(ch); };
  }

  onMembersChange(albumId, cb) {
    let cancelled = false;
    const reload = async () => {
      if (cancelled) return;
      try { cb(await this.listMembers(albumId)); }
      catch (err) { console.error("onMembersChange reload error", err); }
    };
    reload();
    const ch = this.client
      .channel("members:" + albumId)
      .on("postgres_changes", { event: "*", schema: "public", table: "album_members", filter: `album_id=eq.${albumId}` }, reload)
      .subscribe();
    this._channels.push(ch);
    return () => { cancelled = true; this.client.removeChannel(ch); };
  }

  onFriendsChange(albumId, cb) {
    let cancelled = false;
    let friendIds = [];
    let stickerCh = null;

    const subscribeFriendStickers = () => {
      if (stickerCh) this.client.removeChannel(stickerCh);
      if (!friendIds.length) { stickerCh = null; return; }
      stickerCh = this.client
        .channel("friend-stickers:" + albumId)
        .on("postgres_changes",
          { event: "*", schema: "public", table: "stickers", filter: `album_id=in.(${friendIds.join(",")})` },
          reload)
        .subscribe();
    };

    const reload = async () => {
      if (cancelled) return;
      try {
        const friends = await this.listFriendAlbums(albumId);
        const ids = friends.map(f => f.id);
        const newKey = [...ids].sort().join(",");
        const oldKey = [...friendIds].sort().join(",");
        if (newKey !== oldKey) { friendIds = ids; subscribeFriendStickers(); }
        cb(friends);
      } catch (err) { console.error("onFriendsChange reload error", err); }
    };

    reload();
    const ch = this.client
      .channel("friendships:" + albumId)
      .on("postgres_changes", { event: "*", schema: "public", table: "friendships", filter: `album_a=eq.${albumId}` }, reload)
      .on("postgres_changes", { event: "*", schema: "public", table: "friendships", filter: `album_b=eq.${albumId}` }, reload)
      .subscribe();
    this._channels.push(ch);

    return () => {
      cancelled = true;
      this.client.removeChannel(ch);
      if (stickerCh) this.client.removeChannel(stickerCh);
    };
  }
}

// ============================================================================
//  Fábrica
// ============================================================================
export async function createStore() {
  if (isSupabaseConfigured()) {
    const sb = new SupabaseBackend();
    await sb.init();
    return { backend: sb, mode: "supabase", total: TOTAL_STICKERS };
  }
  return { backend: new LocalBackend(), mode: "demo", total: TOTAL_STICKERS };
}
