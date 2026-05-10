# ⚽ Álbum Mundial — Control de Láminas

App web para controlar tu álbum del Mundial 2026 con tu familia y amigos:
marca pegadas/faltantes/repetidas, encuentra **matches automáticos de
intercambio** y comparte por **WhatsApp** con un click.

- ✅ Sin servidor propio. Sin costo.
- ✅ Login con Google (Firebase) o **modo demo** en local.
- ✅ Sincroniza en tiempo real entre tu celular y el de la familia.
- ✅ 980 láminas (configurable en `js/firebase-config.js`).
- ✅ Móvil, responsive, oscuro y bonito.

---

## 🚀 Probar en 30 segundos (modo demo)

No necesitas configurar nada. Solo abre el sitio:

```bash
cd album-mundial
python3 -m http.server 8080
# o:  npx serve .
```

Abre <http://localhost:8080> y dale a *"Probar en modo demo"*.
Tus datos se guardan en `localStorage` del navegador (solo este dispositivo).

> **Limitación del modo demo:** los amigos solo se ven si usan el mismo
> navegador. Para sincronizar entre dispositivos, configura Firebase ⬇️.

---

## 🔥 Activar Firebase (gratis, recomendado)

### 1. Crear el proyecto

1. Entra a <https://console.firebase.google.com> con tu cuenta de Google.
2. **Add project** → ponle un nombre (ej. `album-mundial-familia`).
3. Puedes desactivar Google Analytics si quieres (no lo usamos).

### 2. Habilitar Authentication

1. En el menú lateral: **Build → Authentication → Get started**.
2. Pestaña *Sign-in method* → activa **Google**. Soporta tu correo de soporte y guarda.

### 3. Habilitar Firestore

1. **Build → Firestore Database → Create database**.
2. Modo **production** (con las reglas que pondremos después).
3. Elige la región más cercana (ej. `southamerica-east1` o `us-east1`).

### 4. Registrar una app web

1. En *Project settings* (engranaje arriba a la izquierda) → **General**.
2. Baja a *Your apps* → ícono **`</>`** (web).
3. Apodo: `album-web`. **No** marques Firebase Hosting (lo configuramos aparte si quieres).
4. Copia el bloque `firebaseConfig` que te muestra.

### 5. Pegar credenciales en el proyecto

Edita `js/firebase-config.js` y reemplaza los `PASTE_HERE` con tus valores:

```js
export const firebaseConfig = {
  apiKey: "AIzaSyXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX",
  authDomain: "album-mundial-familia.firebaseapp.com",
  projectId: "album-mundial-familia",
  storageBucket: "album-mundial-familia.appspot.com",
  messagingSenderId: "123456789012",
  appId: "1:123456789012:web:abc123def456",
};
```

> Estas credenciales son **públicas** (van en el cliente). La seguridad real
> está en las reglas de Firestore (`firestore.rules`).

### 6. Subir las reglas de Firestore

Copia el contenido de `firestore.rules` y pégalo en
**Firestore Database → Rules**. Dale *Publish*.

(O usa la CLI: `firebase deploy --only firestore:rules`.)

### 7. Autorizar tu dominio

En **Authentication → Settings → Authorized domains** agrega el dominio donde
vas a hostear (ej. `tuusuario.github.io` o `album.tudominio.com`).
`localhost` ya viene autorizado para desarrollo.

---

## 🌐 Publicar online (gratis)

Elige una de estas opciones:

### Opción A — GitHub Pages (la más simple)

1. Sube el repo a GitHub.
2. **Settings → Pages → Source: `main` branch / folder: `/album-mundial`**.
3. Listo: tu app está en `https://<usuario>.github.io/<repo>/album-mundial/`.

### Opción B — Firebase Hosting

```bash
npm i -g firebase-tools
firebase login
firebase use --add        # selecciona tu proyecto
firebase deploy --only hosting
```

URL: `https://<project-id>.web.app`.

### Opción C — Netlify / Vercel / Cloudflare Pages

Arrastra la carpeta `album-mundial` a cualquiera de ellas. Es estático puro.

---

## 🕹️ Cómo se usa

### Marcar láminas

- **Click**: alterna entre estados → `falta` → `pegada` → `repetida ×2` → `×3` → ... → `×6` → vuelve a `falta`.
- **Click derecho** (escritorio) o **mantener presionado** (móvil): borra esa lámina (vuelve a faltante).

### Buscar
Escribe el número en el cuadro de búsqueda y la app salta a esa lámina y la resalta.

### Amigos
1. En la pestaña **Amigos**, comparte tu *código de invitación* (6 letras/números) por WhatsApp con un click.
2. Cuando un amigo te dé el suyo, pégalo y pulsa *Agregar*.
3. Tu álbum y el suyo se ven en *Intercambios* automáticamente.

### Intercambios
La pestaña **Intercambios** muestra para cada amigo:

- *Le doy*: tus repetidas que a él le faltan.
- *Me da*: sus repetidas que a ti te faltan.

Un botón arma un mensaje listo para WhatsApp con el listado.

---

## 🛠️ Personalización

- **Cambiar número de láminas**: `js/firebase-config.js → TOTAL_STICKERS`.
- **Cargar nombres de jugadores**: aún no implementado en v1; cuando consigas
  la lista oficial podemos cargarla y mostrar el nombre/equipo en cada celda.
- **Cambiar paleta**: variables CSS al inicio de `css/styles.css`.

---

## 📁 Estructura

```
album-mundial/
├── index.html            # Login
├── album.html            # App principal
├── css/styles.css        # Tema oscuro deportivo
├── js/
│   ├── firebase-config.js  # ← edita esto con tus credenciales
│   ├── store.js            # Capa de datos (Firebase o localStorage)
│   ├── auth.js             # Login
│   └── album.js            # App
├── firestore.rules       # Seguridad de la BD
├── firebase.json         # Config para Firebase Hosting
└── README.md
```

---

## 🤝 Roadmap (ideas futuras)

- [ ] Lista oficial de jugadores con nombre y equipo.
- [ ] Foto/escaneo de la lámina para autodetectar el número.
- [ ] Notificaciones push cuando un amigo agrega una repetida que tú necesitas.
- [ ] PWA: instalable y offline.
- [ ] Migración a Supabase si se aprovecha la cuenta Pro.

---

Hecho con cariño para el álbum familiar ⚽
