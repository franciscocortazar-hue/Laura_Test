# ⚽ Álbum Mundial — Control de Láminas

App web para controlar tu álbum Panini Mundial 2026 con tu familia y amigos:
marca pegadas / faltantes / repetidas, encuentra **matches automáticos de
intercambio** y comparte por **WhatsApp** con un click.

- ✅ Static (HTML + CSS + JS modules). Sin build, sin Node.
- ✅ Backend en **Supabase** (Auth con Google + Postgres + Realtime).
- ✅ Modo demo con `localStorage` si aún no configuras Supabase.
- ✅ 980 láminas (configurable).
- ✅ Móvil y responsive, tema oscuro.

---

## 🚀 Probar en 30 segundos (modo demo)

No necesitas configurar nada:

```bash
cd album-mundial
python3 -m http.server 8080
# o:  npx serve .
```

Abre <http://localhost:8080> y pulsa **"Probar en modo demo"**.
Tus datos se guardan en `localStorage` solo en este navegador.

> **Limitación del demo:** los amigos solo se ven si entran desde el mismo
> navegador. Para sincronizar entre dispositivos, configura Supabase ⬇️.

---

## 🟢 Configurar Supabase (en tu cuenta existente)

### 1. Crear el proyecto

1. Entra a <https://supabase.com/dashboard>.
2. **New project** → escoge tu organización (la que tienes Pro), ponle nombre
   (ej. `album-mundial`), genera una contraseña fuerte para Postgres.
3. Región más cercana (ej. *South America (São Paulo)*).

### 2. Aplicar el schema y las políticas

1. Abre **SQL Editor → New query**.
2. Pega el contenido completo de [`supabase-schema.sql`](./supabase-schema.sql) y dale **Run**.
3. Crea las tablas `users`, `stickers`, `friendships`, habilita Realtime y
   aplica las RLS policies. Es idempotente — se puede correr varias veces.

### 3. Activar Google como provider de Auth

1. **Authentication → Providers → Google → Enable**.
2. Sigue la guía de Supabase para crear credenciales OAuth en Google Cloud
   (es un wizard de 5 min). Pega *Client ID* y *Client Secret*.
3. **Authentication → URL Configuration**:
   - *Site URL*: el dominio donde vas a publicar (ej. `https://<usuario>.github.io/album-mundial/`).
   - *Redirect URLs*: agrega esa misma URL y `http://localhost:8080/*` para desarrollo.

### 4. Pegar credenciales en el proyecto

En **Project Settings → API** copia:
- *Project URL*
- *Project API keys → anon public*

Edita `js/supabase-config.js`:

```js
export const supabaseConfig = {
  url: "https://abcd1234.supabase.co",
  anonKey: "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.…",
};
```

> El `anon key` es **público** (va en el cliente); la seguridad real está en
> las RLS policies que ya cargaste.

¡Listo! Abre la app, dale a *"Continuar con Google"* y debería funcionar.

---

## 🌐 Publicar en GitHub Pages (repo aparte)

Como esto vive hoy bajo `Laura_Test/album-mundial/`, te recomiendo moverlo a
**su propio repo**. Una vez allí, GitHub Pages se activa en un click.

### Opción A — Nuevo repo `album-mundial`

URL final: `https://<usuario>.github.io/album-mundial/`

```bash
# desde tu máquina
mkdir ~/github/album-mundial
cp -R /ruta/a/Laura_Test/album-mundial/. ~/github/album-mundial/
cd ~/github/album-mundial
git init
git add .
git commit -m "Initial: World Cup 2026 sticker album"
git branch -M main
# Crea el repo en GitHub (vacío) y luego:
git remote add origin git@github.com:<usuario>/album-mundial.git
git push -u origin main
```

Activa Pages: **Settings → Pages → Source: `main` / root** → Save.
A los ~30s tu app está online.

### Opción B — Reusar tu repo `claudefire`

URL final: `https://<usuario>.github.io/claudefire/album-mundial/`

```bash
cp -R /ruta/a/Laura_Test/album-mundial ~/github/claudefire/
cd ~/github/claudefire
git add album-mundial
git commit -m "Add World Cup 2026 sticker album"
git push
```

Activa Pages como arriba. Recuerda agregar la URL final en Supabase →
*Authentication → URL Configuration* (Site URL + Redirect URLs).

### Opción C — Subdominio personalizado

Si tienes dominio propio, agrégalo en Pages (`Settings → Pages → Custom domain`)
y en Supabase como Site URL.

---

## 🕹️ Cómo se usa

### Marcar láminas

- **Click**: alterna estados → `falta` → `pegada` → `repetida ×2` → `×3` → ... → `×6` → vuelve a `falta`.
- **Click derecho** (escritorio) o **mantener presionado** (móvil): borra la lámina (regresa a faltante).

### Buscar
Escribe el número y la app salta a esa lámina y la resalta.

### Amigos
1. Tab **Amigos** → comparte tu *código de invitación* (6 letras/números) por WhatsApp.
2. Cuando un amigo te dé el suyo, pégalo y pulsa *Agregar*.
3. Sus repes/faltantes salen en **Intercambios**.

### Intercambios
Para cada amigo te muestra:
- *Le doy*: tus repetidas que a él le faltan.
- *Me da*: sus repetidas que a ti te faltan.

Un botón arma el mensaje listo para WhatsApp.

---

## 🛠️ Personalización

- **Número de láminas**: `js/supabase-config.js → TOTAL_STICKERS`.
- **Cargar nombres de jugadores**: aún no en v1. Cuando consigas la lista
  oficial podemos cargarla y mostrar nombre/equipo en cada celda.
- **Paleta**: variables CSS al inicio de `css/styles.css`.

---

## 📁 Estructura

```
album-mundial/
├── index.html               # Login
├── album.html               # App principal
├── css/styles.css           # Tema oscuro deportivo
├── js/
│   ├── supabase-config.js   # ← edita esto con tu URL + anon key
│   ├── store.js             # Capa de datos (Supabase / localStorage)
│   ├── auth.js              # Login
│   └── album.js             # App
├── supabase-schema.sql      # SQL + RLS (correr una vez en Supabase)
└── README.md
```

---

## 🛡️ Seguridad

- El `anon key` se expone (es lo normal en Supabase).
- Todas las tablas tienen **RLS habilitado**.
- `users` y `stickers` son legibles por cualquier autenticado (necesario para
  buscar por código y calcular intercambios), pero solo modificables por el
  dueño.
- `friendships` solo es legible/modificable por las dos partes.

Si en el futuro quieres ocultar el álbum de extraños, podemos restringir
lectura solo a *amigos confirmados* con una policy más estricta.

---

## 🤝 Roadmap

- [ ] Lista oficial de jugadores con nombre y equipo.
- [ ] Foto/scan de la lámina para autodetectar el número.
- [ ] Notificación push cuando un amigo agrega una repe que tú necesitas.
- [ ] PWA instalable / modo offline.

---

Hecho con cariño para el álbum familiar ⚽
