// Pantalla de login. Maneja:
//  1) Google OAuth (dueño del álbum).
//  2) Sign-in anónimo + join a álbum familiar por código (familia sin Google).
//  3) Modo demo (sin nada).

import { isSupabaseConfigured } from "./supabase-config.js";
import { createStore } from "./store.js";

const $ = (sel) => document.querySelector(sel);

const $google = $("#btn-google");
const $join   = $("#btn-join");
const $demo   = $("#btn-demo");
const $hint   = $("#supabase-hint");

if (!isSupabaseConfigured()) {
  $google.disabled = true;
  $join.disabled   = true;
  $hint.hidden = false;
}

// Si ya hay una sesión activa, saltar directo al álbum.
// EXCEPCIÓN: usuarios anónimos sin álbum (sesiones huérfanas) deben quedarse
// en login para que peguen un código.
async function shouldAutoRedirect(store, session) {
  if (!session) return false;
  const user = session.user;
  if (!user.is_anonymous) return true; // Google: siempre.
  try {
    const albums = await store.backend.listAlbumsForUser(user.id);
    return albums.length > 0;
  } catch { return false; }
}

(async function autoRedirectIfSignedIn() {
  if (!isSupabaseConfigured()) return;
  try {
    const store = await createStore();
    const { data } = await store.backend.client.auth.getSession();
    if (await shouldAutoRedirect(store, data?.session)) {
      location.replace("./album.html");
      return;
    }
    store.backend.client.auth.onAuthStateChange(async (_event, session) => {
      if (await shouldAutoRedirect(store, session)) location.replace("./album.html");
    });
  } catch (err) { console.warn("autoRedirect skipped:", err); }
})();

// ---------- Google ----------
$google.addEventListener("click", async () => {
  $google.disabled = true;
  const original = $google.innerHTML;
  $google.textContent = "Abriendo Google…";
  try {
    const store = await createStore();
    await store.backend.loginWithGoogle();
  } catch (err) {
    console.error(err);
    alert("No pudimos iniciar sesión con Google: " + (err?.message || err));
    $google.disabled = false;
    $google.innerHTML = original;
  }
});

// ---------- Modo demo ----------
$demo.addEventListener("click", async () => {
  const store = await createStore();
  let uid = store.backend.getSessionUid?.();
  if (!uid) {
    uid = "demo-" + Math.random().toString(36).slice(2, 10);
    store.backend.setSessionUid(uid);
  }
  await store.backend.ensureDefaultAlbum(uid, "Tú (demo)");
  location.href = "./album.html";
});

// ---------- Modal de "Entrar a álbum familiar" ----------
const $modal     = $("#join-modal");
const $code      = $("#join-code");
const $name      = $("#join-name");
const $msg       = $("#join-msg");
const $btnGo     = $("#btn-join-go");
const $btnCancel = $("#btn-join-cancel");
const $btnClose  = $("#btn-join-close");

function openJoin()  { $modal.classList.remove("hidden"); $code.value = ""; $name.value = ""; $msg.textContent = ""; $msg.className = "form-msg"; setTimeout(() => $code.focus(), 50); }
function closeJoin() { $modal.classList.add("hidden"); }

$join.addEventListener("click", openJoin);
$btnCancel.addEventListener("click", closeJoin);
$btnClose.addEventListener("click", closeJoin);
$modal.addEventListener("click", (e) => { if (e.target === $modal) closeJoin(); });

[$code, $name].forEach(el => el.addEventListener("keydown", (e) => {
  if (e.key === "Enter") { e.preventDefault(); $btnGo.click(); }
}));

$btnGo.addEventListener("click", async () => {
  const code = $code.value.trim().toUpperCase();
  const name = $name.value.trim();
  $msg.className = "form-msg";
  if (!code) { $msg.textContent = "Escribe el código."; $msg.classList.add("err"); return; }
  if (!name) { $msg.textContent = "Escribe tu nombre.";  $msg.classList.add("err"); return; }

  $btnGo.disabled = true;
  $btnGo.textContent = "Entrando…";
  let signedInThisAttempt = false;
  try {
    const store = await createStore();

    let user = (await store.backend.client.auth.getUser()).data?.user;
    if (!user) {
      user = await store.backend.loginAnonymously();
      signedInThisAttempt = true;
    }
    await store.backend.ensureUser(user.id);

    const result = await store.backend.joinAlbumByCode(user.id, code, name);
    if (!result.ok) {
      // Si acabamos de crear una sesión anónima sólo para este intento,
      // ciérrala para no dejar usuarios huérfanos.
      if (signedInThisAttempt) {
        try { await store.backend.logout(); } catch {}
      }
      if (result.reason === "not_found") {
        $msg.textContent = "No encontramos un álbum con ese código.";
      } else {
        $msg.textContent = "No pudimos entrar: " + result.reason;
      }
      $msg.classList.add("err");
      $btnGo.disabled = false;
      $btnGo.textContent = "Entrar";
      return;
    }

    localStorage.setItem("album-mundial:active-album", result.album.id);
    location.replace("./album.html");
  } catch (err) {
    console.error(err);
    if (signedInThisAttempt) {
      try { const s = await createStore(); await s.backend.logout(); } catch {}
    }
    $msg.textContent = "Ups: " + (err?.message || err);
    $msg.classList.add("err");
    $btnGo.disabled = false;
    $btnGo.textContent = "Entrar";
  }
});
