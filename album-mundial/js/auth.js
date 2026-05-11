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
(async function autoRedirectIfSignedIn() {
  if (!isSupabaseConfigured()) return;
  try {
    const store = await createStore();
    const { data } = await store.backend.client.auth.getSession();
    if (data?.session) { location.replace("./album.html"); return; }
    store.backend.client.auth.onAuthStateChange((_event, session) => {
      if (session) location.replace("./album.html");
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
  try {
    const store = await createStore();

    // 1) Verifica que el álbum existe antes de crear cualquier sesión.
    //    (Puede que el cliente todavía no tenga JWT — los SELECT en albums son
    //    públicos para authenticated, así que abajo iniciamos sesión primero
    //    y luego buscamos.)
    let user = (await store.backend.client.auth.getUser()).data?.user;
    if (!user) {
      user = await store.backend.loginAnonymously();
    }
    await store.backend.ensureUser(user.id);

    const result = await store.backend.joinAlbumByCode(user.id, code, name);
    if (!result.ok) {
      // Si veníamos de un signInAnonymously recién creado, mejor cerrar sesión
      // para no dejar huecos.
      if (result.reason === "not_found") {
        $msg.textContent = "No encontramos un álbum con ese código.";
        $msg.classList.add("err");
        $btnGo.disabled = false;
        $btnGo.textContent = "Entrar";
        return;
      }
      throw new Error("join failed: " + result.reason);
    }

    // Guardar el album_id como "álbum activo" para que album.html sepa cuál cargar.
    localStorage.setItem("album-mundial:active-album", result.album.id);
    location.replace("./album.html");
  } catch (err) {
    console.error(err);
    $msg.textContent = "Ups: " + (err?.message || err);
    $msg.classList.add("err");
    $btnGo.disabled = false;
    $btnGo.textContent = "Entrar";
  }
});
