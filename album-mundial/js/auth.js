// Página de login. Maneja Google (si Supabase está configurado) y modo demo.
import { isSupabaseConfigured } from "./supabase-config.js";
import { createStore } from "./store.js";

const $google = document.getElementById("btn-google");
const $demo   = document.getElementById("btn-demo");
const $hint   = document.getElementById("firebase-hint");

if (!isSupabaseConfigured()) {
  $google.disabled = true;
  $hint.hidden = false;
}

// Si Supabase ya tiene una sesión activa (porque venimos de un redirect de Google
// o porque el usuario ya entró antes), saltar directo al álbum.
(async function autoRedirectIfSignedIn() {
  if (!isSupabaseConfigured()) return;
  const store = await createStore();
  const { data } = await store.backend.client.auth.getSession();
  if (data?.session) {
    location.replace("./album.html");
    return;
  }
  store.backend.client.auth.onAuthStateChange((_event, session) => {
    if (session) location.replace("./album.html");
  });
})();

$google.addEventListener("click", async () => {
  $google.disabled = true;
  $google.textContent = "Abriendo Google…";
  try {
    const store = await createStore();
    await store.backend.loginWithGoogle();
    // OAuth redirige al callback. No hace falta navegar manualmente.
  } catch (err) {
    console.error(err);
    alert("No pudimos iniciar sesión con Google: " + (err?.message || err));
    $google.disabled = false;
    $google.innerHTML = '<span class="g-icon">G</span> Continuar con Google';
  }
});

$demo.addEventListener("click", async () => {
  const store = await createStore();
  let uid = store.backend.getSessionUid?.();
  if (!uid) {
    uid = "demo-" + Math.random().toString(36).slice(2, 10);
    store.backend.setSessionUid(uid);
  }
  await store.backend.ensureUser({
    uid,
    displayName: "Tú (demo)",
    photoURL: "",
  });
  location.href = "./album.html";
});
