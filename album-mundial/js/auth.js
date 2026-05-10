// Página de login. Maneja Google (si Firebase está configurado) y modo demo.
import { isFirebaseConfigured } from "./firebase-config.js";
import { createStore } from "./store.js";

const $google = document.getElementById("btn-google");
const $demo   = document.getElementById("btn-demo");
const $hint   = document.getElementById("firebase-hint");

if (!isFirebaseConfigured()) {
  $google.disabled = true;
  $hint.hidden = false;
}

$google.addEventListener("click", async () => {
  $google.disabled = true;
  $google.textContent = "Abriendo Google…";
  try {
    const store = await createStore();
    const user = await store.backend.loginWithGoogle();
    await store.backend.ensureUser({
      uid: user.uid,
      displayName: user.displayName,
      photoURL: user.photoURL,
    });
    location.href = "./album.html";
  } catch (err) {
    console.error(err);
    alert("No pudimos iniciar sesión con Google: " + (err?.message || err));
    $google.disabled = false;
    $google.innerHTML = '<span class="g-icon">G</span> Continuar con Google';
  }
});

$demo.addEventListener("click", async () => {
  const store = await createStore();
  // En modo demo, creamos un usuario local con un uid persistente para este navegador.
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
