// App principal: grid por secciones, tabs, amigos, intercambios y WhatsApp.
import { isSupabaseConfigured } from "./supabase-config.js";
import { createStore } from "./store.js";
import { SECTIONS, STICKERS, BY_SECTION, TOTAL_STICKERS, findByCode, shortLabel } from "./album-structure.js";

// ---------- Constantes y helpers ----------
const STATUS = { MISSING: 0, OWNED: 1, DUPLICATE: 2 };
const MAX_DUP = 6;

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

// Agrupa una lista de sticker objects por sección y devuelve líneas legibles
// para WhatsApp, p.ej.: "*México:* 1, 5, 12-14".
function groupBySectionForShare(stickers) {
  if (!stickers.length) return ["—"];
  const buckets = new Map(); // section_id → { name, nums }
  // Preservar orden de SECTIONS
  for (const s of stickers) {
    if (!buckets.has(s.section_id)) {
      buckets.set(s.section_id, { name: s.section_name, nums: [] });
    }
    buckets.get(s.section_id).nums.push(s.n);
  }
  const lines = [];
  for (const sec of SECTIONS) {
    const b = buckets.get(sec.section_id);
    if (!b) continue;
    lines.push(`• *${b.name}*: ${compactNumberList(b.nums)}`);
  }
  return lines;
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
  profile: null,        // { uid, displayName, photoURL, inviteCode, stickers: { "CODE": {s,c} } }
  friends: [],
  filter: "all",
  search: "",
  tab: "album",
};

// ---------- Boot ----------
(async function boot() {
  state.store = await createStore();

  if (state.store.mode === "supabase") {
    const { data } = await state.store.backend.client.auth.getSession();
    const session = data?.session;
    if (!session) { location.replace("./index.html"); return; }

    const user = session.user;
    state.uid = user.id;
    const meta = user.user_metadata || {};
    await state.store.backend.ensureUser({
      uid: user.id,
      displayName: meta.full_name || meta.name || user.email || "Sin nombre",
      photoURL: meta.avatar_url || meta.picture || "",
    });

    state.store.backend.client.auth.onAuthStateChange((event) => {
      if (event === "SIGNED_OUT") location.replace("./index.html");
    });

    attachSubscriptions();
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
  $$(".tab").forEach(t => t.addEventListener("click", (e) => {
    e.preventDefault();
    setTab(t.dataset.tab);
  }));
  if (location.hash) setTab(location.hash.slice(1));

  $$(".chip[data-filter]").forEach(c => c.addEventListener("click", () => {
    $$(".chip[data-filter]").forEach(x => x.classList.remove("active"));
    c.classList.add("active");
    state.filter = c.dataset.filter;
    applyFilter();
  }));

  // Búsqueda por código (MEX5, ARG3, FWC9, 00, etc.)
  const $search = $("#search-input");
  $search.addEventListener("input", (e) => {
    state.search = e.target.value;
    const sticker = findByCode(state.search);
    if (!sticker) return;
    const cell = document.querySelector(`.cell[data-code="${sticker.code}"]`);
    if (cell) {
      // Asegura que la sección esté visible aunque haya filtro
      const sec = cell.closest(".album-section");
      if (sec) sec.style.display = "";
      cell.style.display = "";
      cell.scrollIntoView({ behavior: "smooth", block: "center" });
      cell.classList.remove("hilite"); void cell.offsetWidth; cell.classList.add("hilite");
    }
  });

  $("#btn-logout").addEventListener("click", async () => {
    if (state.store.mode === "supabase") {
      await state.store.backend.logout();
    } else {
      state.store.backend.clearSession();
    }
    location.href = "./index.html";
  });

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
    for (const section of SECTIONS) {
      const stickers = BY_SECTION.get(section.section_id);
      const sec = document.createElement("section");
      sec.className = "album-section";
      sec.dataset.section = section.section_id;

      const header = document.createElement("h2");
      header.className = "section-header";
      const range = section.section_id === "panini"
        ? "00"
        : `${section.code_prefix}${section.from}–${section.code_prefix}${section.to}`;
      header.innerHTML = `<span>${escapeHTML(section.section_name)}</span><small>${range}</small>`;
      sec.appendChild(header);

      const cells = document.createElement("div");
      cells.className = "cells";
      for (const s of stickers) {
        const cell = document.createElement("button");
        cell.className = "cell";
        cell.dataset.code = s.code;
        cell.title = s.code;
        cell.innerHTML = `<span class="num">${shortLabel(s)}</span>`;
        cell.addEventListener("click", () => cycleSticker(s.code));
        cell.addEventListener("contextmenu", (e) => { e.preventDefault(); resetSticker(s.code); });
        // Long-press móvil
        let timer = null;
        cell.addEventListener("touchstart", () => {
          timer = setTimeout(() => { resetSticker(s.code); timer = null; }, 550);
        }, { passive: true });
        cell.addEventListener("touchend",  () => { if (timer) clearTimeout(timer); });
        cell.addEventListener("touchmove", () => { if (timer) clearTimeout(timer); });
        cells.appendChild(cell);
      }
      sec.appendChild(cells);
      frag.appendChild(sec);
    }
    grid.appendChild(frag);
    gridBuilt = true;
  }
  // Pinta estados
  const owned = state.profile?.stickers || {};
  for (const s of STICKERS) {
    const cell = document.querySelector(`.cell[data-code="${s.code}"]`);
    if (cell) paintCell(cell, owned[s.code]);
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
  $$(".album-section").forEach(sec => {
    let visible = 0;
    sec.querySelectorAll(".cell").forEach(c => {
      const s = c.dataset.status || "missing";
      const show = f === "all" || s === f;
      c.style.display = show ? "" : "none";
      if (show) visible++;
    });
    sec.style.display = visible === 0 ? "none" : "";
  });
}

async function cycleSticker(code) {
  if (!state.profile) return;
  const cur = state.profile.stickers[code] || { s: 0, c: 0 };
  let next;
  if (cur.s === STATUS.MISSING) next = { s: STATUS.OWNED, c: 0 };
  else if (cur.s === STATUS.OWNED) next = { s: STATUS.DUPLICATE, c: 2 };
  else if (cur.s === STATUS.DUPLICATE && (cur.c || 2) < MAX_DUP) next = { s: STATUS.DUPLICATE, c: (cur.c || 2) + 1 };
  else next = { s: STATUS.MISSING, c: 0 };

  if (next.s === STATUS.MISSING) delete state.profile.stickers[code];
  else state.profile.stickers[code] = next;
  paintCell(document.querySelector(`.cell[data-code="${code}"]`), state.profile.stickers[code]);
  renderStats();
  applyFilter();

  await state.store.backend.setSticker(state.uid, code, next.s, next.c);
}

async function resetSticker(code) {
  if (!state.profile) return;
  delete state.profile.stickers[code];
  paintCell(document.querySelector(`.cell[data-code="${code}"]`), null);
  renderStats();
  applyFilter();
  await state.store.backend.setSticker(state.uid, code, 0, 0);
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
  const missing = TOTAL_STICKERS - owned;
  const progress = Math.round((owned / TOTAL_STICKERS) * 100);
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
        <span class="sub">Código ${f.inviteCode || "—"} · ${countOwned(f.stickers)} / ${TOTAL_STICKERS} pegadas</span>
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
  const my = state.profile?.stickers || {};
  let anyMatch = false;

  for (const f of state.friends) {
    const fSt = f.stickers || {};
    const iCanGive = [];   // sticker objects
    const heCanGive = [];
    for (const s of STICKERS) {
      const me = my[s.code];
      const fr = fSt[s.code];
      const meDup   = me?.s === STATUS.DUPLICATE;
      const meNeeds = !me || me.s === STATUS.MISSING;
      const frDup   = fr?.s === STATUS.DUPLICATE;
      const frNeeds = !fr || fr.s === STATUS.MISSING;
      if (meDup && frNeeds) iCanGive.push(s);
      if (frDup && meNeeds) heCanGive.push(s);
    }
    if (!iCanGive.length && !heCanGive.length) continue;
    anyMatch = true;

    const card = document.createElement("div");
    card.className = "match";
    const give = iCanGive.length ? groupBySectionForShare(iCanGive).join("<br>") : "—";
    const get  = heCanGive.length ? groupBySectionForShare(heCanGive).join("<br>") : "—";
    card.innerHTML = `
      <header>
        <img alt="" ${f.photoURL ? `src="${f.photoURL}"` : ""} />
        <h3>${escapeHTML(f.displayName || "Amigo")}</h3>
      </header>
      <div class="rows">
        <div class="row">
          <span class="label">Le doy (${iCanGive.length})</span>
          <span class="nums">${give}</span>
        </div>
        <div class="row">
          <span class="label">Me da (${heCanGive.length})</span>
          <span class="nums">${get}</span>
        </div>
      </div>
      <div class="actions">
        <button class="btn btn-primary" data-act="wa">📲 Mensaje WhatsApp</button>
        <button class="btn btn-ghost" data-act="copy">Copiar listado</button>
      </div>
    `;
    card.querySelector('[data-act="wa"]').addEventListener("click", () => {
      openShareModal(buildTradeText(f, iCanGive, heCanGive));
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
  const owned = state.profile?.stickers || {};
  const missing = [], dupes = [];
  for (const s of STICKERS) {
    const st = owned[s.code];
    if (!st || st.s === STATUS.MISSING) missing.push(s);
    else if (st.s === STATUS.DUPLICATE) dupes.push(s);
  }
  const ownedCount = TOTAL_STICKERS - missing.length;
  const name = state.profile?.displayName || "Yo";
  return [
    `⚽ *Álbum Mundial 2026* — ${name}`,
    `Llevo *${ownedCount}/${TOTAL_STICKERS}* pegadas (${Math.round(ownedCount*100/TOTAL_STICKERS)}%).`,
    ``,
    `🔁 *Repetidas que tengo (${dupes.length}):*`,
    ...(dupes.length ? groupBySectionForShare(dupes) : ["Ninguna por ahora"]),
    ``,
    `🙏 *Me faltan (${missing.length}):*`,
    ...(missing.length ? groupBySectionForShare(missing) : ["¡Ninguna! Álbum lleno 🏆"]),
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
    `🔁 *Yo te doy (${iCanGive.length}):*`,
    ...(iCanGive.length ? groupBySectionForShare(iCanGive) : ["—"]),
    ``,
    `🤝 *Tú me das (${heCanGive.length}):*`,
    ...(heCanGive.length ? groupBySectionForShare(heCanGive) : ["—"]),
    ``,
    `¿Cuándo nos vemos para cambiar?`,
  ].join("\n");
}

function openShareModal(text) {
  $("#share-text").value = text;
  $("#btn-share-open").href = `https://wa.me/?text=${encodeURIComponent(text)}`;
  $("#share-modal").classList.remove("hidden");
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

if (!isSupabaseConfigured()) {
  console.info("[Álbum] Modo demo activo. Configura Supabase para sincronizar entre dispositivos. Ver README.md");
}
