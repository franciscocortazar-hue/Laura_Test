// App principal del álbum compartido.
import { isSupabaseConfigured } from "./supabase-config.js";
import { createStore } from "./store.js";
import { SECTIONS, STICKERS, BY_SECTION, TOTAL_STICKERS, findByCode, shortLabel, prefixEmoji } from "./album-structure.js";

const STATUS = { MISSING: 0, OWNED: 1, DUPLICATE: 2 };
const MAX_DUP = 6;
const ACTIVE_ALBUM_KEY = "album-mundial:active-album";

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

// Agrupa por PREFIJO (estilo Figuritas App): "MEX 🇲🇽: 1, 5, 12-14".
// Las 3 secciones FWC (intro, hosts, history) colapsan en una sola línea "FWC 📜".
// El sticker de Panini se muestra como "Panini ⭐".
function groupByPrefixForShare(stickers) {
  if (!stickers.length) return ["—"];
  const order = []; // mantiene orden de aparición (= orden de álbum)
  const buckets = new Map(); // key (prefix or "panini") → { label, emoji, nums }
  for (const s of stickers) {
    const isPanini = s.section_id === "panini";
    const key = isPanini ? "panini" : s.prefix;
    if (!buckets.has(key)) {
      buckets.set(key, {
        label: isPanini ? "Panini" : s.prefix,
        emoji: isPanini ? "⭐" : prefixEmoji(s.prefix),
        nums: [],
      });
      order.push(key);
    }
    buckets.get(key).nums.push(s.n);
  }
  return order.map(k => {
    const b = buckets.get(k);
    return `${b.label} ${b.emoji}: ${compactNumberList(b.nums)}`;
  });
}

function openWhatsApp(text, phone = "") {
  const url = phone
    ? `https://wa.me/${phone.replace(/[^0-9]/g, "")}?text=${encodeURIComponent(text)}`
    : `https://wa.me/?text=${encodeURIComponent(text)}`;
  window.open(url, "_blank", "noopener");
}

function escapeHTML(s) {
  return String(s).replace(/[&<>"']/g, c => ({
    "&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#39;",
  })[c]);
}

// ---------- Estado ----------
const state = {
  store: null,
  uid: null,
  myName: "",
  album: null,          // { id, owner_id, name, invite_code, stickers: { code: {s,c} } }
  members: [],          // [{ album_id, user_id, member_name, joined_at }]
  friends: [],          // álbumes externos
  filter: "all",
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
    await state.store.backend.ensureUser(user.id);

    state.store.backend.client.auth.onAuthStateChange((event) => {
      if (event === "SIGNED_OUT") location.replace("./index.html");
    });

    // Decidir álbum activo:
    //  - Si el usuario marcó uno como activo (vino de "join"), úsalo.
    //  - Si no, listar álbumes en los que es miembro.
    //  - Si está en alguno, pick el primero.
    //  - Si no está en ninguno (es la primera vez con Google), crearle uno.
    const meta = user.user_metadata || {};
    const displayName = meta.full_name || meta.name || user.email || "Yo";
    const isAnonymous = !!user.is_anonymous;

    let albumId = localStorage.getItem(ACTIVE_ALBUM_KEY);
    let memberAlbums = await state.store.backend.listAlbumsForUser(user.id);
    if (albumId && !memberAlbums.find(a => a.id === albumId)) albumId = null;

    if (!albumId) {
      if (memberAlbums.length) {
        albumId = memberAlbums[0].id;
      } else if (isAnonymous) {
        // Anónimo sin álbum: probablemente la sesión quedó huérfana de un
        // intento fallido. NO crear álbum nuevo (eso lleva a álbumes "Yo"
        // fantasma). Mejor cerrar sesión y mandarlo a pegar un código.
        await state.store.backend.logout();
        localStorage.removeItem(ACTIVE_ALBUM_KEY);
        location.replace("./index.html");
        return;
      } else {
        // Usuario Google nuevo: créale su propio álbum.
        const created = await state.store.backend.ensureDefaultAlbum(user.id, displayName);
        albumId = created.id;
      }
      localStorage.setItem(ACTIVE_ALBUM_KEY, albumId);
    }

    state.albumId = albumId;
    state.myName = displayName;
  } else {
    state.uid = state.store.backend.getSessionUid();
    if (!state.uid) { location.href = "./index.html"; return; }
    const album = await state.store.backend.ensureDefaultAlbum(state.uid, "Tú (demo)");
    state.albumId = album.id;
    state.myName = "Tú (demo)";
  }

  attachSubscriptions();
  wireUI();
})();

function attachSubscriptions() {
  state.store.backend.onAlbumChange(state.albumId, (album) => {
    if (!album) return;
    state.album = { ...album, stickers: album.stickers || {} };
    renderHeader();
    renderInvite();
    renderGrid();
    renderStats();
    renderMatches();
  });
  state.store.backend.onMembersChange(state.albumId, (members) => {
    state.members = members;
    renderMembers();
    renderUserChip();
  });
  state.store.backend.onFriendsChange(state.albumId, (friends) => {
    state.friends = friends;
    renderFriendAlbums();
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

  $("#search-input").addEventListener("input", (e) => {
    const sticker = findByCode(e.target.value);
    if (!sticker) return;
    const cell = document.querySelector(`.cell[data-code="${sticker.code}"]`);
    if (cell) {
      const sec = cell.closest(".album-section");
      if (sec) sec.style.display = "";
      cell.style.display = "";
      cell.scrollIntoView({ behavior: "smooth", block: "center" });
      cell.classList.remove("hilite"); void cell.offsetWidth; cell.classList.add("hilite");
    }
  });

  $("#btn-logout").addEventListener("click", async () => {
    if (state.store.mode === "supabase") await state.store.backend.logout();
    else state.store.backend.clearSession();
    localStorage.removeItem(ACTIVE_ALBUM_KEY);
    location.href = "./index.html";
  });

  $("#btn-copy-code").addEventListener("click", () => {
    const code = state.album?.invite_code || "";
    navigator.clipboard.writeText(code);
    toast("Código copiado: " + code);
  });
  $("#btn-share-code").addEventListener("click", () => {
    const code = state.album?.invite_code || "";
    const url = `${location.origin}${location.pathname.replace(/album\.html$/, "")}`;
    const txt = `¡Hola! Te invito a llenar conmigo el álbum del Mundial 2026 ⚽\n\nEntra aquí: ${url}\n\nToca "Entrar a álbum familiar (con código)" y pega:\n\n*${code}*\n\n¡Listo, ya estamos llenando el mismo álbum!`;
    openWhatsApp(txt);
  });

  $("#btn-add-friend").addEventListener("click", addFriendAlbumFromInput);
  $("#friend-code").addEventListener("keydown", (e) => { if (e.key === "Enter") addFriendAlbumFromInput(); });

  $("#btn-clear-all").addEventListener("click", async () => {
    const total = Object.keys(state.album?.stickers || {}).length;
    if (total === 0) { toast("El álbum ya está vacío."); return; }
    const ok = confirm(
      `¿Borrar las ${total} láminas marcadas del álbum compartido?\n\n` +
      `Esto afecta a TODOS los miembros y NO se puede deshacer.`
    );
    if (!ok) return;
    const btn = $("#btn-clear-all");
    btn.disabled = true;
    const original = btn.textContent;
    btn.textContent = "Borrando…";
    try {
      await state.store.backend.clearAllStickers(state.albumId);
      // Optimistic local clear; el realtime las repintará a faltantes igualmente.
      if (state.album) state.album.stickers = {};
      renderGrid(); renderStats();
      toast("Álbum reiniciado");
    } catch (err) {
      console.error(err);
      alert("No pudimos borrar: " + (err?.message || err));
    } finally {
      btn.disabled = false;
      btn.textContent = original;
    }
  });

  // Botón principal: abre modal con modo "ambos" por defecto.
  $("#btn-share-whatsapp").addEventListener("click", () => {
    _activeShareMode = "both";
    openShareModal(buildMyShareText("both"), { showModes: true });
  });
  // Atajos directos a cada modo (faltantes / repes / ambos)
  $("#btn-share-missing")?.addEventListener("click", () => {
    _activeShareMode = "missing";
    openShareModal(buildMyShareText("missing"), { showModes: true });
  });
  $("#btn-share-duplicates")?.addEventListener("click", () => {
    _activeShareMode = "duplicate";
    openShareModal(buildMyShareText("duplicate"), { showModes: true });
  });

  // Chips dentro del modal para cambiar de modo sin cerrarlo.
  document.addEventListener("click", (e) => {
    const chip = e.target.closest?.("#share-modes .chip");
    if (!chip) return;
    _activeShareMode = chip.dataset.mode || "both";
    document.querySelectorAll("#share-modes .chip").forEach(c => {
      c.classList.toggle("active", c === chip);
    });
    const text = buildMyShareText(_activeShareMode);
    $("#share-text").value = text;
    $("#btn-share-open").href = `https://wa.me/?text=${encodeURIComponent(text)}`;
  });

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

async function addFriendAlbumFromInput() {
  const input = $("#friend-code");
  const msg = $("#friend-msg");
  msg.className = "form-msg";
  const code = input.value.trim().toUpperCase();
  if (!code) { msg.textContent = "Escribe un código."; msg.classList.add("err"); return; }
  if (code === state.album?.invite_code) {
    msg.textContent = "Ese es el código de TU álbum 😄"; msg.classList.add("err"); return;
  }
  const other = await state.store.backend.findAlbumByCode(code);
  if (!other) { msg.textContent = "No encontramos ese código."; msg.classList.add("err"); return; }
  const added = await state.store.backend.addFriendship(state.albumId, other.id);
  if (!added) { msg.textContent = "Ya estaban conectados."; msg.classList.add("ok"); return; }
  msg.textContent = `¡Listo! Conectaste con "${other.name}".`;
  msg.classList.add("ok");
  input.value = "";
}

// ---------- Tabs ----------
function setTab(name) {
  if (!["album", "amigos", "intercambios"].includes(name)) name = "album";
  state.tab = name;
  $$(".tab").forEach(t => t.classList.toggle("active", t.dataset.tab === name));
  $$(".view").forEach(v => v.classList.toggle("hidden", v.dataset.view !== name));
  history.replaceState(null, "", "#" + name);
}

// ---------- Render: header ----------
function renderHeader() {
  if (!state.album) return;
  const title = state.album.name || "Álbum Mundial";
  $("#album-title").textContent = title;
  document.title = `${title} — Mundial 2026`;
}

function renderUserChip() {
  // Muestra el nombre del MIEMBRO (no del Google user) en el chip.
  const me = state.members.find(m => m.user_id === state.uid);
  const name = me?.member_name || state.myName || "Yo";
  $("#user-name").textContent = name;
  $("#user-avatar").style.display = "none";
}

// ---------- Render: invite + miembros ----------
function renderInvite() {
  $("#my-invite-code").textContent = state.album?.invite_code || "------";
}

function renderMembers() {
  const ul = $("#members-list");
  ul.innerHTML = "";
  if (!state.members.length) {
    ul.innerHTML = '<li class="empty">Sin miembros todavía.</li>';
    return;
  }
  const ownerId = state.album?.owner_id;
  for (const m of state.members) {
    const li = document.createElement("li");
    const isMe = m.user_id === state.uid;
    const isOwner = m.user_id === ownerId;
    li.innerHTML = `
      <img alt="" style="display:none" />
      <div class="meta">
        <span class="name">${escapeHTML(m.member_name || "Miembro")} ${isMe ? '<small class="muted">(tú)</small>' : ''} ${isOwner ? '<small class="muted">— dueño</small>' : ''}</span>
        <span class="sub">Unido ${new Date(m.joined_at).toLocaleDateString()}</span>
      </div>
    `;
    ul.appendChild(li);
  }
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
        // Click avanza estado. La X (renderizada en celdas marcadas) borra.
        // Click-derecho y long-press móvil también borran.
        cell.addEventListener("click", () => cycleSticker(s.code));
        cell.addEventListener("contextmenu", (e) => { e.preventDefault(); resetSticker(s.code); });
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
  const owned = state.album?.stickers || {};
  for (const s of STICKERS) {
    const cell = document.querySelector(`.cell[data-code="${s.code}"]`);
    if (cell) paintCell(cell, owned[s.code]);
  }
  applyFilter();
}

function paintCell(cell, st) {
  cell.classList.remove("owned", "duplicate");
  cell.dataset.status = "missing";
  cell.querySelector(".dup-badge")?.remove();
  cell.querySelector(".del-x")?.remove();
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
    badge.title = "Toca para bajar el contador";
    badge.addEventListener("click", (e) => {
      e.stopPropagation();
      decrementSticker(cell.dataset.code);
    });
    cell.appendChild(badge);
  }

  // Botón ✕ para borrar (visible siempre que la celda esté marcada).
  const del = document.createElement("span");
  del.className = "del-x";
  del.textContent = "✕";
  del.setAttribute("role", "button");
  del.setAttribute("aria-label", "Borrar lámina");
  del.addEventListener("click", (e) => {
    e.stopPropagation();
    resetSticker(cell.dataset.code);
  });
  cell.appendChild(del);
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
  if (!state.album) return;
  const cur = state.album.stickers[code] || { s: 0, c: 0 };
  let next;
  if (cur.s === STATUS.MISSING) next = { s: STATUS.OWNED, c: 0 };
  else if (cur.s === STATUS.OWNED) next = { s: STATUS.DUPLICATE, c: 2 };
  else if (cur.s === STATUS.DUPLICATE && (cur.c || 2) < MAX_DUP) next = { s: STATUS.DUPLICATE, c: (cur.c || 2) + 1 };
  else next = { s: STATUS.MISSING, c: 0 };

  if (next.s === STATUS.MISSING) delete state.album.stickers[code];
  else state.album.stickers[code] = next;
  paintCell(document.querySelector(`.cell[data-code="${code}"]`), state.album.stickers[code]);
  renderStats();
  applyFilter();

  await state.store.backend.setSticker(state.albumId, code, next.s, next.c);
}

async function resetSticker(code) {
  if (!state.album) return;
  delete state.album.stickers[code];
  paintCell(document.querySelector(`.cell[data-code="${code}"]`), null);
  renderStats();
  applyFilter();
  await state.store.backend.setSticker(state.albumId, code, 0, 0);
}

// Quita una repe (x3→x2, x2→pegada). Útil al intercambiar una repetida.
async function decrementSticker(code) {
  if (!state.album) return;
  const cur = state.album.stickers[code];
  if (!cur || cur.s !== STATUS.DUPLICATE) return;
  const c = cur.c || 2;
  let next;
  if (c > 2) next = { s: STATUS.DUPLICATE, c: c - 1 };
  else next = { s: STATUS.OWNED, c: 0 };

  state.album.stickers[code] = next;
  paintCell(document.querySelector(`.cell[data-code="${code}"]`), next);
  renderStats();
  applyFilter();
  await state.store.backend.setSticker(state.albumId, code, next.s, next.c);
}

// ---------- Render: stats ----------
function renderStats() {
  const stickers = state.album?.stickers || {};
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

// ---------- Render: álbumes externos ----------
function renderFriendAlbums() {
  const ul = $("#friends-list");
  ul.innerHTML = "";
  if (!state.friends.length) {
    ul.innerHTML = '<li class="empty">Aún no tienes álbumes conectados.</li>';
    return;
  }
  for (const a of state.friends) {
    const li = document.createElement("li");
    li.innerHTML = `
      <img alt="" style="display:none" />
      <div class="meta">
        <span class="name">${escapeHTML(a.name || "Álbum")}</span>
        <span class="sub">Código ${a.invite_code || "—"} · ${countOwned(a.stickers)} / ${TOTAL_STICKERS} pegadas</span>
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
    wrap.innerHTML = '<div class="empty">Conecta álbumes externos en la tab "Miembros y Amigos" para ver intercambios.</div>';
    return;
  }
  const my = state.album?.stickers || {};
  let anyMatch = false;

  for (const a of state.friends) {
    const fSt = a.stickers || {};
    const iCanGive = [];
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
    const give = iCanGive.length ? groupByPrefixForShare(iCanGive).join("<br>") : "—";
    const get  = heCanGive.length ? groupByPrefixForShare(heCanGive).join("<br>") : "—";
    card.innerHTML = `
      <header>
        <img alt="" style="display:none" />
        <h3>${escapeHTML(a.name || "Álbum")}</h3>
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
      openShareModal(buildTradeText(a, iCanGive, heCanGive), { showModes: false });
    });
    card.querySelector('[data-act="copy"]').addEventListener("click", async () => {
      await navigator.clipboard.writeText(buildTradeText(a, iCanGive, heCanGive));
      toast("Texto copiado");
    });
    wrap.appendChild(card);
  }
  if (!anyMatch) {
    wrap.innerHTML = '<div class="empty">Por ahora no hay matches con tus álbumes conectados.</div>';
  }
}

// ---------- Compartir ----------
// Construye uno de tres reportes: solo faltantes, solo repetidas, o ambos.
// Formato Figuritas-style: una línea por prefijo con bandera.
function buildMyShareText(mode /* "missing" | "duplicate" | "both" */) {
  const owned = state.album?.stickers || {};
  const missing = [], dupes = [];
  for (const s of STICKERS) {
    const st = owned[s.code];
    if (!st || st.s === STATUS.MISSING) missing.push(s);
    else if (st.s === STATUS.DUPLICATE) dupes.push(s);
  }
  const ownedCount = TOTAL_STICKERS - missing.length;
  const name = state.album?.name || "Nuestro álbum";
  const header = [
    `⚽ *${name}* — Mundial 2026`,
    `Llevamos *${ownedCount}/${TOTAL_STICKERS}* pegadas (${Math.round(ownedCount*100/TOTAL_STICKERS)}%).`,
    ``,
  ];

  const blockMissing = () => [
    `🙏 *Me faltan (${missing.length}):*`,
    ...(missing.length ? groupByPrefixForShare(missing) : ["¡Ninguna! Álbum lleno 🏆"]),
  ];
  const blockDupes = () => [
    `🔁 *Tengo repetidas (${dupes.length}):*`,
    ...(dupes.length ? groupByPrefixForShare(dupes) : ["Ninguna por ahora"]),
  ];

  let body;
  if (mode === "missing")       body = blockMissing();
  else if (mode === "duplicate") body = blockDupes();
  else                           body = [...blockDupes(), ``, ...blockMissing()];

  return [...header, ...body, ``, `¿Cambiamos? 🤝`].join("\n");
}

function buildTradeText(friendAlbum, iCanGive, heCanGive) {
  const name = friendAlbum.name || "vecino";
  return [
    `¡Hola ${name}! ⚽`,
    `Mira los intercambios que tenemos para el álbum del Mundial 2026:`,
    ``,
    `🔁 *Yo te doy (${iCanGive.length}):*`,
    ...(iCanGive.length ? groupByPrefixForShare(iCanGive) : ["—"]),
    ``,
    `🤝 *Tú me das (${heCanGive.length}):*`,
    ...(heCanGive.length ? groupByPrefixForShare(heCanGive) : ["—"]),
    ``,
    `¿Cuándo nos vemos para cambiar?`,
  ].join("\n");
}

// Estado del modal: qué modo está activo (afecta solo a "mi" reporte).
let _activeShareMode = "both";

function openShareModal(text, opts = {}) {
  $("#share-text").value = text;
  $("#btn-share-open").href = `https://wa.me/?text=${encodeURIComponent(text)}`;
  $("#share-modal").classList.remove("hidden");

  // Mostrar / ocultar selector según el contexto. Sólo lo activamos cuando
  // compartimos "lo mío" (no para intercambios con un amigo específico).
  const modeRow = $("#share-modes");
  if (modeRow) {
    if (opts.showModes) {
      modeRow.classList.remove("hidden");
      // Pinta el chip activo
      modeRow.querySelectorAll(".chip").forEach(c => {
        c.classList.toggle("active", c.dataset.mode === _activeShareMode);
      });
    } else {
      modeRow.classList.add("hidden");
    }
  }

  $("#share-text").oninput = () => {
    $("#btn-share-open").href = `https://wa.me/?text=${encodeURIComponent($("#share-text").value)}`;
  };
}
function closeShareModal() {
  $("#share-modal").classList.add("hidden");
}

if (!isSupabaseConfigured()) {
  console.info("[Álbum] Modo demo activo. Configura Supabase para sincronizar. Ver README.md");
}
