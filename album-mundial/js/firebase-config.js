// Pega aquí la configuración de tu proyecto Firebase (Console > Settings > General > Tu app web).
// Mientras no la pegues, la app corre en MODO DEMO usando localStorage.
export const firebaseConfig = {
  apiKey: "PASTE_HERE",
  authDomain: "PASTE_HERE",
  projectId: "PASTE_HERE",
  storageBucket: "PASTE_HERE",
  messagingSenderId: "PASTE_HERE",
  appId: "PASTE_HERE",
};

// Número total de láminas del álbum Panini Mundial 2026 (incluye especiales).
export const TOTAL_STICKERS = 980;

export const isFirebaseConfigured = () =>
  !!firebaseConfig.apiKey && !firebaseConfig.apiKey.startsWith("PASTE");
