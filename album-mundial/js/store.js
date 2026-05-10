// Capa de datos: usa Firebase si está configurado, si no, localStorage (modo demo).
// La interfaz pública es la misma para que el resto de la app no sepa qué backend hay debajo.

import { firebaseConfig, isFirebaseConfigured, TOTAL_STICKERS } from "./firebase-config.js";

const LS_KEY = "album-mundial:v1";
const DEMO_SESSION_KEY = "album-mundial:session";

function makeInviteCode() {
  // 6 caracteres alfanuméricos, sin caracteres confusos (0, O, I, 1).
  const ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789";
  let s = "";
  for (let i = 0; i < 6; i++) s += ALPHABET[Math.floor(Math.random() * ALPHABET.length)];
  return s;
}

function emptyStickers() {
  // Estructura: { "1": { s: 0, c: 0 }, ... }  s = status (0=missing,1=owned,2=duplicate)
  return {};
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

  // ---- Sesión ----
  getSessionUid() {
    return localStorage.getItem(DEMO_SESSION_KEY);
  }
  setSessionUid(uid) {
    localStorage.setItem(DEMO_SESSION_KEY, uid);
  }
  clearSession() {
    localStorage.removeItem(DEMO_SESSION_KEY);
  }

  ensureUser(profile) {
    const uid = profile.uid;
    if (!this.data.users[uid]) {
      this.data.users[uid] = {
        uid,
        displayName: profile.displayName || "Sin nombre",
        photoURL: profile.photoURL || "",
        inviteCode: makeInviteCode(),
        stickers: emptyStickers(),
        createdAt: Date.now(),
      };
      this._write();
    } else {
      // Refresca campos cambiantes.
      this.data.users[uid].displayName = profile.displayName || this.data.users[uid].displayName;
      this.data.users[uid].photoURL = profile.photoURL || this.data.users[uid].photoURL;
      this._write();
    }
    return this.data.users[uid];
  }

  getProfile(uid) { return this.data.users[uid] || null; }

  setSticker(uid, n, status, count) {
    const u = this.data.users[uid];
    if (!u) return;
    if (status === 0) delete u.stickers[n];
    else u.stickers[n] = { s: status, c: count };
    this._write();
  }

  findUserByCode(code) {
    code = (code || "").toUpperCase();
    return Object.values(this.data.users).find(u => u.inviteCode === code) || null;
  }

  addFriendship(a, b) {
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

  onUserChange(_uid, cb)   { cb(this.getProfile(_uid)); return () => {}; }
  onFriendsChange(uid, cb) { cb(this.listFriends(uid)); return () => {}; }
}

// ============================================================================
//  Backend: FIREBASE (Firestore + Auth)
// ============================================================================
class FirebaseBackend {
  constructor() {
    this.app = null;
    this.auth = null;
    this.db = null;
    this._unsubProfile = null;
    this._unsubFriends = null;
  }

  async init() {
    const [{ initializeApp }, authMod, dbMod] = await Promise.all([
      import("https://www.gstatic.com/firebasejs/10.12.4/firebase-app.js"),
      import("https://www.gstatic.com/firebasejs/10.12.4/firebase-auth.js"),
      import("https://www.gstatic.com/firebasejs/10.12.4/firebase-firestore.js"),
    ]);
    this.app = initializeApp(firebaseConfig);
    this.auth = authMod.getAuth(this.app);
    this.db   = dbMod.getFirestore(this.app);
    this._authMod = authMod;
    this._dbMod   = dbMod;
  }

  async loginWithGoogle() {
    const provider = new this._authMod.GoogleAuthProvider();
    const res = await this._authMod.signInWithPopup(this.auth, provider);
    return res.user;
  }
  async logout() {
    await this._authMod.signOut(this.auth);
  }

  onAuthChanged(cb) {
    return this._authMod.onAuthStateChanged(this.auth, cb);
  }

  async ensureUser(profile) {
    const { doc, getDoc, setDoc, updateDoc, serverTimestamp } = this._dbMod;
    const ref = doc(this.db, "users", profile.uid);
    const snap = await getDoc(ref);
    if (!snap.exists()) {
      // Genera un inviteCode único (intentos limitados).
      let code = makeInviteCode();
      for (let i = 0; i < 5; i++) {
        const { collection, query, where, getDocs } = this._dbMod;
        const q = query(collection(this.db, "users"), where("inviteCode", "==", code));
        const found = await getDocs(q);
        if (found.empty) break;
        code = makeInviteCode();
      }
      await setDoc(ref, {
        uid: profile.uid,
        displayName: profile.displayName || "Sin nombre",
        photoURL: profile.photoURL || "",
        inviteCode: code,
        createdAt: serverTimestamp(),
      });
    } else {
      await updateDoc(ref, {
        displayName: profile.displayName || snap.data().displayName,
        photoURL: profile.photoURL || snap.data().photoURL || "",
      });
    }
    const fresh = await getDoc(ref);
    return fresh.data();
  }

  async getProfile(uid) {
    const { doc, getDoc } = this._dbMod;
    const snap = await getDoc(doc(this.db, "users", uid));
    return snap.exists() ? snap.data() : null;
  }

  async setSticker(uid, n, status, count) {
    const { doc, setDoc, deleteDoc } = this._dbMod;
    const ref = doc(this.db, "users", uid, "stickers", String(n));
    if (status === 0) await deleteDoc(ref);
    else await setDoc(ref, { s: status, c: count, n: Number(n) });
  }

  async getStickers(uid) {
    const { collection, getDocs } = this._dbMod;
    const snap = await getDocs(collection(this.db, "users", uid, "stickers"));
    const out = {};
    snap.forEach(d => { out[d.id] = d.data(); });
    return out;
  }

  async findUserByCode(code) {
    code = (code || "").toUpperCase();
    const { collection, query, where, getDocs, limit } = this._dbMod;
    const q = query(collection(this.db, "users"), where("inviteCode", "==", code), limit(1));
    const snap = await getDocs(q);
    return snap.empty ? null : snap.docs[0].data();
  }

  async addFriendship(a, b) {
    if (a === b) return false;
    const { doc, setDoc, serverTimestamp } = this._dbMod;
    // ID determinista para que el par sea único.
    const id = [a, b].sort().join("__");
    await setDoc(doc(this.db, "friendships", id), {
      users: [a, b].sort(),
      createdAt: serverTimestamp(),
    });
    return true;
  }

  onUserChange(uid, cb) {
    const { doc, onSnapshot, collection } = this._dbMod;
    const unsubProfile = onSnapshot(doc(this.db, "users", uid), async (snap) => {
      const profile = snap.exists() ? snap.data() : null;
      if (!profile) { cb(null); return; }
      profile.stickers = await this.getStickers(uid);
      cb(profile);
    });
    const unsubStickers = onSnapshot(collection(this.db, "users", uid, "stickers"), async () => {
      const profile = await this.getProfile(uid);
      if (!profile) return;
      profile.stickers = await this.getStickers(uid);
      cb(profile);
    });
    return () => { unsubProfile(); unsubStickers(); };
  }

  onFriendsChange(uid, cb) {
    const { collection, query, where, onSnapshot } = this._dbMod;
    const q = query(collection(this.db, "friendships"), where("users", "array-contains", uid));
    return onSnapshot(q, async (snap) => {
      const friendIds = [];
      snap.forEach(d => {
        const users = d.data().users;
        friendIds.push(users[0] === uid ? users[1] : users[0]);
      });
      const friends = await Promise.all(friendIds.map(async fid => {
        const p = await this.getProfile(fid);
        if (!p) return null;
        p.stickers = await this.getStickers(fid);
        return p;
      }));
      cb(friends.filter(Boolean));
    });
  }
}

// ============================================================================
//  Fábrica
// ============================================================================
export async function createStore() {
  if (isFirebaseConfigured()) {
    const fb = new FirebaseBackend();
    await fb.init();
    return { backend: fb, mode: "firebase", total: TOTAL_STICKERS };
  }
  return { backend: new LocalBackend(), mode: "demo", total: TOTAL_STICKERS };
}
