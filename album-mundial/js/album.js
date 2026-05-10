// App principal: grid, tabs, amigos, intercambios y WhatsApp.
import { isSupabaseConfigured } from "./supabase-config.js";
import { createStore } from "./store.js";

// ---------- Constantes y helpers ----------
const STATUS = { MISSING: 0, OWNED: 1, DUPLICATE: 2 };
const MAX_DUP = 6; // tope visible antes de "rotar" al ciclo

function $(sel) { return document.querySelector(sel); }
function $$(sel) { return Array.from(document.querySelectorAll(sel)); }

function toast(msg, ms = 1800) {
  let el = document.querySelector(".toast");
  if (!el) { el = document.createElement("div"); el.className = "toast"; document.body.appendChild(el); }
  el.textContent = msg;
  requestAnimationFrame(() => el.classList.add("show"));
  clearTimeout(toast._t);
  toast._t = setTimeout(() => el.classList.remove("show"), ms);
}

function compactNumberList(nums) {
  // Convierte [1,2,3,5,7,8,9] → "1-3, 5, 7-9"
  if (!nums.length) return "—";
  const sorted = [...nums].sort((a, b) => a - b);
  const ranges = [];
  let start = sorted[0], prev = sorted[0];
  for (let i = 1; i < sorted.length; i++) {
    if (sorted[i] === prev + 1) { prev = sorted[i]; continue; }
    ranges.push(start === prev ? `${start}` : `${start}-${prev}`);
    start = prev = sorted[i];
  }
  ranges.push(start === prev ? `${start}` : `${start}-${prev}`);
  return ranges.join(", ");
}

function openWhatsApp(text, phone = "") {
  const url = phone
    ? `https://wa.me/${phone.replace(/[^0-9]/g, "")}?text=${encodeURIComponent(text)}`
    : `https://wa.me/?text=${encodeURIComponent(text)}`;
  window.open(url, "_blank", "noopener");
}

// ---------- Estado ----------
const state = {
  store: null,
  uid: null,
  profile: null,        // { uid, displayName, photoURL, inviteCode, stickers: { "n": {s,c} } }
  friends: [],
  filter: "all",
  search: "",
  tab: "album",
};

// ---------- Boot ----------
(async function boot() {
  state.store = await createStore();

  if (state.store.mode === "supabase") {
    state.store.backend.onAuthChanged(async (user) => {
      if (!user) { location.href = "./index.html"; return; }
      state.uid = user.id;
      const meta = user.user_metadata || {};
      await state.store.backend.ensureUser({
        uid: user.id,
        displayName: meta.full_name || meta.name || user.email || "Sin nombre",
        photoURL: meta.avatar_url || meta.picture || "",
      });
      attachSubscriptions();
    });
  } else {
    state.uid = state.store.backend.getSessionUid();
    if (!state.uid) { location.href = "./index.html"; return; }
    attachSubscriptions();
  }

  wireUI();
})();

function attachSubscriptions() {
  state.store.backend.onUserChange(state.uid, async (profile) => {
    if (!profile) return;
    // En modo demo, los stickers ya vienen embebidos. En Firebase, también (los hidratamos).
    state.profile = { ...profile, stickers: profile.stickers || {} };
    renderUserChip();
    renderGrid();
    renderStats();
    renderInvite();
    renderMatches();
  });
  state.store.backend.onFriendsChange(state.uid, (friends) => {
    state.friends = friends;
    renderFriends();
    renderMatches();
  });
}

// ---------- UI Wiring ----------
function wireUI() {
  // Tabs
  $$(".tab").forEach(t => t.addEventListener("click", (e) => {
    e.preventDefault();
    setTab(t.dataset.tab);
  }));
  // Permite navegación con hash (e.g., #amigos)
  if (location.hash) setTab(location.hash.slice(1));

  // Filtros
  $$(".chip[data-filter]").forEach(c => c.addEventListener("click", () => {
    $$(".chip[data-filter]").forEach(x => x.classList.remove("active"));
    c.classList.add("active");
    state.filter = c.dataset.filter;
    applyFilter();
  }));

  // Búsqueda
  $("#search-input").addEventListener("input", (e) => {
    state.search = e.target.value.trim();
    if (!state.search) return;
    const n = Number(state.search);
    if (!Number.isFinite(n) || n < 1 || n > state.store.total) return;
    const cell = document.querySelector(`.cell[data-n="${n}"]`);
    if (cell) {
      cell.scrollIntoView({ behavior: "smooth", block: "center" });
      cell.classList.remove("hilite"); void cell.offsetWidth; cell.classList.add("hilite");
    }
  });

  // Logout
  $("#btn-logout").addEventListener("click", async () => {
    if (state.store.mode === "supabase") {
      await state.store.backend.logout();
    } else {
      state.store.backend.clearSession();
    }
    location.href = "./index.html";
  });

  // Amigos
  $("#btn-copy-code").addEventListener("click", () => {
    const code = state.profile?.inviteCode || "";
    navigator.clipboard.writeText(code);
    toast("Código copiado: " + code);
  });
  $("#btn-share-code").addEventListener("click", () => {
    const code = state.profile?.inviteCode || "";
    const txt = `¡Hola! Te invito a mi álbum del Mundial 2026 ⚽\n\nÚsalo para registrar tus repetidas y faltantes y cambiar conmigo.\n\nMi código: *${code}*\n\nEntra aquí: ${location.origin}${location.pathname.replace(/album\.html$/, "")}`;
    openWhatsApp(txt);
  });
  $("#btn-add-friend").addEventListener("click", addFriendFromInput);
  $("#friend-code").addEventListener("keydown", (e) => {
    if (e.key === "Enter") addFriendFromInput();
  });

  // Compartir general
  $("#btn-share-whatsapp").addEventListener("click", () => openShareModal(buildMyShareText()));
  $("#btn-share-close").addEventListener("click", closeShareModal);
  $("#btn-share-copy").addEventListener("click", async () => {
    await navigator.clipboard.writeText($("#share-text").value);
    toast("Texto copiado");
  });
  $("#btn-share-open").addEventListener("click", (e) => {
    e.preventDefault();
    openWhatsApp($("#share-text").value);
  });
}

async function addFriendFromInput() {
  const input = $("#friend-code");
  const msg = $("#friend-msg");
  msg.className = "form-msg";
  const code = input.value.trim().toUpperCase();
  if (!code) { msg.textContent = "Escribe un código."; msg.classList.add("err"); return; }
  if (code === state.profile.inviteCode) {
    msg.textContent = "Ese es tu propio código 😄"; msg.classList.add("err"); return;
  }
  const friend = await state.store.backend.findUserByCode(code);
  if (!friend) { msg.textContent = "No encontramos ese código."; msg.classList.add("err"); return; }
  const added = await state.store.backend.addFriendship(state.uid, friend.uid);
  if (!added) { msg.textContent = "Ya eran amigos."; msg.classList.add("ok"); return; }
  msg.textContent = `¡Listo! Conectaste con ${friend.displayName}.`;
  msg.classList.add("ok");
  input.value = "";
  // El listener de friends actualizará la lista; en modo demo lo refrescamos a mano.
  if (state.store.mode === "demo") {
    state.friends = state.store.backend.listFriends(state.uid);
    renderFriends(); renderMatches();
  }
}

// ---------- Tabs ----------
function setTab(name) {
  if (!["album", "amigos", "intercambios"].includes(name)) name = "album";
  state.tab = name;
  $$(".tab").forEach(t => t.classList.toggle("active", t.dataset.tab === name));
  $$(".view").forEach(v => v.classList.toggle("hidden", v.dataset.view !== name));
  history.replaceState(null, "", "#" + name);
}

// ---------- Render: header / chip ----------
function renderUserChip() {
  if (!state.profile) return;
  $("#user-name").textContent = state.profile.displayName || "Sin nombre";
  const img = $("#user-avatar");
  if (state.profile.photoURL) { img.src = state.profile.photoURL; img.style.display = ""; }
  else { img.removeAttribute("src"); img.style.display = "none"; }
}

// ---------- Render: grid ----------
let gridBuilt = false;
function renderGrid() {
  const grid = $("#grid");
  if (!gridBuilt) {
    const frag = document.createDocumentFragment();
    for (let n = 1; n <= state.store.total; n++) {
      const cell = document.createElement("button");
      cell.className = "cell";
      cell.dataset.n = String(n);
      cell.innerHTML = `<span class="num">${n}</span>`;
      cell.addEventListener("click", () => cycleSticker(n));
      cell.addEventListener("contextmenu", (e) => { e.preventDefault(); resetSticker(n); });
      // Long-press para móvil
      let timer = null;
      cell.addEventListener("touchstart", () => {
        timer = setTimeout(() => { resetSticker(n); timer = null; }, 550);
      }, { passive: true });
      cell.addEventListener("touchend", () => { if (timer) clearTimeout(timer); });
      cell.addEventListener("touchmove", () => { if (timer) clearTimeout(timer); });
      frag.appendChild(cell);
    }
    grid.appendChild(frag);
    gridBuilt = true;
  }
  // Pinta estados
  const stickers = state.profile?.stickers || {};
  for (let n = 1; n <= state.store.total; n++) {
    const cell = grid.children[n - 1];
    paintCell(cell, stickers[String(n)]);
  }
  applyFilter();
}

function paintCell(cell, st) {
  cell.classList.remove("owned", "duplicate");
  cell.dataset.status = "missing";
  const existing = cell.querySelector(".dup-badge");
  if (existing) existing.remove();
  if (!st || st.s === STATUS.MISSING) return;
  if (st.s === STATUS.OWNED) {
    cell.classList.add("owned");
    cell.dataset.status = "owned";
  } else if (st.s === STATUS.DUPLICATE) {
    cell.classList.add("duplicate");
    cell.dataset.status = "duplicate";
    const badge = document.createElement("span");
    badge.className = "dup-badge";
    badge.textContent = "x" + Math.max(2, st.c || 2);
    cell.appendChild(badge);
  }
}

function applyFilter() {
  const f = state.filter;
  $$("#grid .cell").forEach(c => {
    const s = c.dataset.status || "missing";
    const show = f === "all" || s === f;
    c.style.display = show ? "" : "none";
  });
}

async function cycleSticker(n) {
  if (!state.profile) return;
  const cur = state.profile.stickers[String(n)] || { s: 0, c: 0 };
  let next;
  if (cur.s === STATUS.MISSING) next = { s: STATUS.OWNED, c: 0 };
  else if (cur.s === STATUS.OWNED) next = { s: STATUS.DUPLICATE, c: 2 };
  else if (cur.s === STATUS.DUPLICATE && (cur.c || 2) < MAX_DUP) next = { s: STATUS.DUPLICATE, c: (cur.c || 2) + 1 };
  else next = { s: STATUS.MISSING, c: 0 };

  // Optimistic update
  if (next.s === STATUS.MISSING) delete state.profile.stickers[String(n)];
  else state.profile.stickers[String(n)] = next;
  paintCell($(`.cell[data-n="${n}"]`), state.profile.stickers[String(n)]);
  renderStats();
  applyFilter();

  await state.store.backend.setSticker(state.uid, n, next.s, next.c);
}

async function resetSticker(n) {
  if (!state.profile) return;
  delete state.profile.stickers[String(n)];
  paintCell($(`.cell[data-n="${n}"]`), null);
  renderStats();
  applyFilter();
  await state.store.backend.setSticker(state.uid, n, 0, 0);
}

// ---------- Render: stats ----------
function renderStats() {
  const stickers = state.profile?.stickers || {};
  let owned = 0, dupes = 0;
  for (const k in stickers) {
    const st = stickers[k];
    if (st.s === STATUS.OWNED) owned++;
    else if (st.s === STATUS.DUPLICATE) { owned++; dupes += Math.max(1, (st.c || 2) - 1); }
  }
  const missing = state.store.total - owned;
  const progress = Math.round((owned / state.store.total) * 100);
  $("#stat-owned").textContent   = owned;
  $("#stat-missing").textContent = missing;
  $("#stat-dupes").textContent   = dupes;
  $("#stat-progress").textContent = progress + "%";
}

// ---------- Render: amigos ----------
function renderInvite() {
  $("#my-invite-code").textContent = state.profile?.inviteCode || "------";
}

function renderFriends() {
  const ul = $("#friends-list");
  ul.innerHTML = "";
  if (!state.friends.length) {
    ul.innerHTML = '<li class="empty">Aún no tienes amigos conectados.</li>';
    return;
  }
  for (const f of state.friends) {
    const li = document.createElement("li");
    li.innerHTML = `
      <img alt="" ${f.photoURL ? `src="${f.photoURL}"` : ""} />
      <div class="meta">
        <span class="name">${escapeHTML(f.displayName || "Sin nombre")}</span>
        <span class="sub">Código ${f.inviteCode || "—"} · ${countOwned(f.stickers)} / ${state.store.total} pegadas</span>
      </div>
    `;
    ul.appendChild(li);
  }
}

function countOwned(map) {
  let n = 0;
  for (const k in (map || {})) {
    const s = map[k]?.s;
    if (s === STATUS.OWNED || s === STATUS.DUPLICATE) n++;
  }
  return n;
}

// ---------- Render: matches ----------
function renderMatches() {
  const wrap = $("#matches");
  wrap.innerHTML = "";
  if (!state.friends.length) {
    wrap.innerHTML = '<div class="empty">Conecta amigos para ver intercambios.</div>';
    return;
  }
  const myStickers = state.profile?.stickers || {};
  let anyMatch = false;

  for (const f of state.friends) {
    const fSt = f.stickers || {};
    const iCanGive = [];   // tengo repe y a él le faltan
    const heCanGive = [];  // él tiene repe y a mí me faltan
    for (let n = 1; n <= state.store.total; n++) {
      const me = myStickers[String(n)];
      const fr = fSt[String(n)];
      const meDup    = me?.s === STATUS.DUPLICATE;
      const meNeeds  = !me || me.s === STATUS.MISSING;
      const frDup    = fr?.s === STATUS.DUPLICATE;
      const frNeeds  = !fr || fr.s === STATUS.MISSING;
      if (meDup && frNeeds) iCanGive.push(n);
      if (frDup && meNeeds) heCanGive.push(n);
    }
    if (!iCanGive.length && !heCanGive.length) continue;
    anyMatch = true;

    const card = document.createElement("div");
    card.className = "match";
    card.innerHTML = `
      <header>
        <img alt="" ${f.photoURL ? `src="${f.photoURL}"` : ""} />
        <h3>${escapeHTML(f.displayName || "Amigo")}</h3>
      </header>
      <div class="rows">
        <div class="row">
          <span class="label">Le doy</span>
          <span class="nums">${iCanGive.length ? compactNumberList(iCanGive) : "—"}</span>
        </div>
        <div class="row">
          <span class="label">Me da</span>
          <span class="nums">${heCanGive.length ? compactNumberList(heCanGive) : "—"}</span>
        </div>
      </div>
      <div class="actions">
        <button class="btn btn-primary" data-act="wa">📲 Mensaje WhatsApp</button>
        <button class="btn btn-ghost" data-act="copy">Copiar listado</button>
      </div>
    `;
    card.querySelector('[data-act="wa"]').addEventListener("click", () => {
      const txt = buildTradeText(f, iCanGive, heCanGive);
      openShareModal(txt);
    });
    card.querySelector('[data-act="copy"]').addEventListener("click", async () => {
      await navigator.clipboard.writeText(buildTradeText(f, iCanGive, heCanGive));
      toast("Texto copiado");
    });
    wrap.appendChild(card);
  }
  if (!anyMatch) {
    wrap.innerHTML = '<div class="empty">Por ahora no hay matches con tus amigos. Cuando alguien tenga una repetida que a otro le falte, aparece aquí.</div>';
  }
}

// ---------- Compartir ----------
function buildMyShareText() {
  const stickers = state.profile?.stickers || {};
  const missing = [], dupes = [];
  for (let n = 1; n <= state.store.total; n++) {
    const st = stickers[String(n)];
    if (!st || st.s === STATUS.MISSING) missing.push(n);
    else if (st.s === STATUS.DUPLICATE) dupes.push(n);
  }
  const owned = state.store.total - missing.length;
  const name = state.profile?.displayName || "Yo";
  return [
    `⚽ *Álbum Mundial 2026* — ${name}`,
    `Llevo *${owned}/${state.store.total}* pegadas (${Math.round(owned*100/state.store.total)}%).`,
    ``,
    `🔁 *Repetidas que tengo:*`,
    dupes.length ? compactNumberList(dupes) : "Ninguna por ahora",
    ``,
    `🙏 *Me faltan:*`,
    missing.length ? compactNumberList(missing) : "¡Ninguna! Álbum lleno 🏆",
    ``,
    `¿Cambiamos? 🤝`,
  ].join("\n");
}

function buildTradeText(friend, iCanGive, heCanGive) {
  const name = friend.displayName || "parcero";
  return [
    `¡Hola ${name}! ⚽`,
    `Mira los intercambios que tenemos para el álbum del Mundial 2026:`,
    ``,
    `🔁 *Yo te doy:*`,
    iCanGive.length ? compactNumberList(iCanGive) : "—",
    ``,
    `🤝 *Tú me das:*`,
    heCanGive.length ? compactNumberList(heCanGive) : "—",
    ``,
    `¿Cuándo nos vemos para cambiar?`,
  ].join("\n");
}

function openShareModal(text) {
  $("#share-text").value = text;
  $("#btn-share-open").href = `https://wa.me/?text=${encodeURIComponent(text)}`;
  $("#share-modal").classList.remove("hidden");
  // Actualiza el link en vivo al editar
  $("#share-text").oninput = () => {
    $("#btn-share-open").href = `https://wa.me/?text=${encodeURIComponent($("#share-text").value)}`;
  };
}
function closeShareModal() {
  $("#share-modal").classList.add("hidden");
}

// ---------- Util ----------
function escapeHTML(s) {
  return String(s).replace(/[&<>"']/g, c => ({
    "&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#39;",
  })[c]);
}

// Hint para usuarios curiosos
if (!isSupabaseConfigured()) {
  console.info("[Álbum] Modo demo activo. Configura Supabase para sincronizar entre dispositivos. Ver README.md");
}
