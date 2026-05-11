// Capa de datos: Supabase si está configurado; si no, localStorage (modo demo).
// La interfaz pública es la misma para que el resto de la app no sepa qué backend hay debajo.

import { supabaseConfig, isSupabaseConfigured } from "./supabase-config.js";
import { TOTAL_STICKERS } from "./album-structure.js";

const LS_KEY = "album-mundial:v1";
const DEMO_SESSION_KEY = "album-mundial:session";

function makeInviteCode() {
  // 6 caracteres alfanuméricos, sin caracteres confusos (0, O, I, 1).
  const ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789";
  let s = "";
  for (let i = 0; i < 6; i++) s += ALPHABET[Math.floor(Math.random() * ALPHABET.length)];
  return s;
}

// ============================================================================
//  Backend: LOCAL (demo / sin login)
// ============================================================================
class LocalBackend {
  constructor() {
    this.data = this._read();
  }
  _read() {
    try {
      const raw = localStorage.getItem(LS_KEY);
      if (!raw) return { users: {}, friendships: [] };
      return JSON.parse(raw);
    } catch {
      return { users: {}, friendships: [] };
    }
  }
  _write() {
    localStorage.setItem(LS_KEY, JSON.stringify(this.data));
  }

  // ---- Sesión demo ----
  getSessionUid() { return localStorage.getItem(DEMO_SESSION_KEY); }
  setSessionUid(uid) { localStorage.setItem(DEMO_SESSION_KEY, uid); }
  clearSession() { localStorage.removeItem(DEMO_SESSION_KEY); }

  async loginWithGoogle() {
    throw new Error("Login con Google requiere Supabase configurado.");
  }
  async logout() { this.clearSession(); }
  onAuthChanged(cb) {
    const uid = this.getSessionUid();
    cb(uid ? { uid } : null);
    return () => {};
  }

  async ensureUser(profile) {
    const uid = profile.uid;
    if (!this.data.users[uid]) {
      this.data.users[uid] = {
        uid,
        displayName: profile.displayName || "Sin nombre",
        photoURL: profile.photoURL || "",
        inviteCode: makeInviteCode(),
        stickers: {},
        createdAt: Date.now(),
      };
      this._write();
    } else {
      this.data.users[uid].displayName = profile.displayName || this.data.users[uid].displayName;
      this.data.users[uid].photoURL = profile.photoURL || this.data.users[uid].photoURL;
      this._write();
    }
    return this.data.users[uid];
  }

  async getProfile(uid) { return this.data.users[uid] || null; }

  async setSticker(uid, code, status, count) {
    const u = this.data.users[uid];
    if (!u) return;
    if (status === 0) delete u.stickers[code];
    else u.stickers[code] = { s: status, c: count };
    this._write();
  }

  async findUserByCode(code) {
    code = (code || "").toUpperCase();
    return Object.values(this.data.users).find(u => u.inviteCode === code) || null;
  }

  async addFriendship(a, b) {
    if (a === b) return false;
    const exists = this.data.friendships.find(f =>
      (f[0] === a && f[1] === b) || (f[0] === b && f[1] === a)
    );
    if (exists) return false;
    this.data.friendships.push([a, b, Date.now()]);
    this._write();
    return true;
  }

  listFriends(uid) {
    const ids = this.data.friendships
      .filter(f => f[0] === uid || f[1] === uid)
      .map(f => (f[0] === uid ? f[1] : f[0]));
    return ids.map(id => this.data.users[id]).filter(Boolean);
  }

  onUserChange(uid, cb)   { cb(this.data.users[uid] || null); return () => {}; }
  onFriendsChange(uid, cb) { cb(this.listFriends(uid)); return () => {}; }
}

// ============================================================================
//  Backend: SUPABASE
// ============================================================================
class SupabaseBackend {
  constructor() {
    this.client = null;
    this._stickerChannel = null;
    this._friendsChannel = null;
    this._friendStickersChannel = null;
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
    // OAuth redirige, no devuelve aquí. Si redirige rápido, el siguiente await nunca corre.
    return null;
  }

  async logout() { await this.client.auth.signOut(); }

  onAuthChanged(cb) {
    // Dispara una vez con la sesión actual y luego escucha cambios.
    this.client.auth.getUser().then(({ data }) => cb(data?.user || null));
    const { data: sub } = this.client.auth.onAuthStateChange((_event, session) => {
      cb(session?.user || null);
    });
    return () => sub.subscription.unsubscribe();
  }

  async _generateUniqueInviteCode() {
    for (let i = 0; i < 8; i++) {
      const code = makeInviteCode();
      const { data, error } = await this.client
        .from("users").select("id").eq("invite_code", code).maybeSingle();
      if (error) throw error;
      if (!data) return code;
    }
    return makeInviteCode(); // fallback (probabilidad de colisión ínfima)
  }

  async ensureUser(profile) {
    const uid = profile.uid;
    const { data: existing, error: e1 } = await this.client
      .from("users").select("*").eq("id", uid).maybeSingle();
    if (e1) throw e1;

    if (!existing) {
      const code = await this._generateUniqueInviteCode();
      const { data, error } = await this.client
        .from("users")
        .insert({
          id: uid,
          display_name: profile.displayName || "Sin nombre",
          photo_url: profile.photoURL || "",
          invite_code: code,
        })
        .select().single();
      if (error) throw error;
      return this._mapUser(data);
    } else {
      const patch = {};
      if (profile.displayName && profile.displayName !== existing.display_name) patch.display_name = profile.displayName;
      if (profile.photoURL && profile.photoURL !== existing.photo_url) patch.photo_url = profile.photoURL;
      if (Object.keys(patch).length) {
        const { data, error } = await this.client
          .from("users").update(patch).eq("id", uid).select().single();
        if (error) throw error;
        return this._mapUser(data);
      }
      return this._mapUser(existing);
    }
  }

  _mapUser(row) {
    if (!row) return null;
    return {
      uid: row.id,
      displayName: row.display_name || "Sin nombre",
      photoURL: row.photo_url || "",
      inviteCode: row.invite_code,
      stickers: {},
    };
  }

  async getProfile(uid) {
    const { data, error } = await this.client.from("users").select("*").eq("id", uid).maybeSingle();
    if (error) throw error;
    return this._mapUser(data);
  }

  async getStickers(uid) {
    const { data, error } = await this.client.from("stickers").select("code, status, count").eq("user_id", uid);
    if (error) throw error;
    const out = {};
    for (const row of (data || [])) out[row.code] = { s: row.status, c: row.count || 0 };
    return out;
  }

  async setSticker(uid, code, status, count) {
    if (status === 0) {
      const { error } = await this.client.from("stickers").delete()
        .eq("user_id", uid).eq("code", code);
      if (error) throw error;
    } else {
      const { error } = await this.client.from("stickers").upsert({
        user_id: uid, code, status, count: count || 0,
      }, { onConflict: "user_id,code" });
      if (error) throw error;
    }
  }

  async findUserByCode(code) {
    code = (code || "").toUpperCase();
    const { data, error } = await this.client
      .from("users").select("*").eq("invite_code", code).maybeSingle();
    if (error) throw error;
    return this._mapUser(data);
  }

  async addFriendship(a, b) {
    if (a === b) return false;
    const [u1, u2] = [a, b].sort();
    const { error } = await this.client.from("friendships")
      .insert({ user_a: u1, user_b: u2 });
    if (error) {
      if (error.code === "23505") return false; // duplicate key
      throw error;
    }
    return true;
  }

  onUserChange(uid, cb) {
    let cancelled = false;

    const reload = async () => {
      if (cancelled) return;
      try {
        const profile = await this.getProfile(uid);
        if (!profile) { cb(null); return; }
        profile.stickers = await this.getStickers(uid);
        cb(profile);
      } catch (err) { console.error("onUserChange reload error", err); }
    };

    reload();
    this._stickerChannel = this.client
      .channel("stickers:" + uid)
      .on("postgres_changes",
        { event: "*", schema: "public", table: "stickers", filter: `user_id=eq.${uid}` },
        reload)
      .on("postgres_changes",
        { event: "*", schema: "public", table: "users", filter: `id=eq.${uid}` },
        reload)
      .subscribe();

    return () => {
      cancelled = true;
      if (this._stickerChannel) this.client.removeChannel(this._stickerChannel);
      this._stickerChannel = null;
    };
  }

  async _listFriendIds(uid) {
    const { data, error } = await this.client
      .from("friendships").select("user_a, user_b")
      .or(`user_a.eq.${uid},user_b.eq.${uid}`);
    if (error) throw error;
    return (data || []).map(r => r.user_a === uid ? r.user_b : r.user_a);
  }

  async _hydrateFriends(uid) {
    const ids = await this._listFriendIds(uid);
    if (!ids.length) return [];
    const { data: profiles, error: e1 } = await this.client
      .from("users").select("*").in("id", ids);
    if (e1) throw e1;
    const { data: stickers, error: e2 } = await this.client
      .from("stickers").select("user_id, code, status, count").in("user_id", ids);
    if (e2) throw e2;
    const byUser = {};
    for (const s of (stickers || [])) {
      (byUser[s.user_id] ||= {})[s.code] = { s: s.status, c: s.count || 0 };
    }
    return (profiles || []).map(p => {
      const u = this._mapUser(p);
      u.stickers = byUser[p.id] || {};
      return u;
    });
  }

  onFriendsChange(uid, cb) {
    let cancelled = false;
    let friendIds = [];
    let stickerChannel = null;

    const subscribeFriendStickers = () => {
      if (stickerChannel) this.client.removeChannel(stickerChannel);
      if (!friendIds.length) { stickerChannel = null; return; }
      stickerChannel = this.client
        .channel("friend-stickers:" + uid)
        .on("postgres_changes",
          { event: "*", schema: "public", table: "stickers",
            filter: `user_id=in.(${friendIds.join(",")})` },
          reload)
        .subscribe();
    };

    const reload = async () => {
      if (cancelled) return;
      try {
        const friends = await this._hydrateFriends(uid);
        const newIds = friends.map(f => f.uid).sort().join(",");
        const oldIds = friendIds.slice().sort().join(",");
        if (newIds !== oldIds) {
          friendIds = friends.map(f => f.uid);
          subscribeFriendStickers();
        }
        cb(friends);
      } catch (err) { console.error("onFriendsChange reload error", err); }
    };

    reload();
    this._friendsChannel = this.client
      .channel("friendships:" + uid)
      .on("postgres_changes",
        { event: "*", schema: "public", table: "friendships", filter: `user_a=eq.${uid}` },
        reload)
      .on("postgres_changes",
        { event: "*", schema: "public", table: "friendships", filter: `user_b=eq.${uid}` },
        reload)
      .subscribe();

    return () => {
      cancelled = true;
      if (this._friendsChannel) this.client.removeChannel(this._friendsChannel);
      if (stickerChannel) this.client.removeChannel(stickerChannel);
      this._friendsChannel = null;
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
