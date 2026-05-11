// Estructura oficial del álbum Panini FIFA World Cup 2026.
// Si Panini lanza una versión distinta o se mueve algo, edita SECTIONS y
// la app reconstruye automáticamente el grid, los códigos y los lookups.

export const SECTIONS = [
  { section_id: "panini",         section_name: "We Are Panini",                  code_prefix: "",    from: 0,  to: 0,  count: 1,  description: "Logo Panini (sticker 00)" },
  { section_id: "intro",          section_name: "Tournament Intro",               code_prefix: "FWC", from: 1,  to: 5,  count: 5,  description: "Emblema, mascotas, eslogan, balón" },
  { section_id: "host_cities",    section_name: "Host Countries & Cities",        code_prefix: "FWC", from: 6,  to: 8,  count: 3,  description: "Emblemas (foil) de Canadá, México, USA" },

  { section_id: "group_a_mex",    section_name: "Grupo A — México",               code_prefix: "MEX", from: 1, to: 20, count: 20, description: "Escudo + foto de equipo + 18 jugadores" },
  { section_id: "group_a_rsa",    section_name: "Grupo A — Sudáfrica",            code_prefix: "RSA", from: 1, to: 20, count: 20, description: "Escudo + foto de equipo + 18 jugadores" },
  { section_id: "group_a_kor",    section_name: "Grupo A — Corea del Sur",        code_prefix: "KOR", from: 1, to: 20, count: 20, description: "Escudo + foto de equipo + 18 jugadores" },
  { section_id: "group_a_cze",    section_name: "Grupo A — Chequia",              code_prefix: "CZE", from: 1, to: 20, count: 20, description: "Escudo + foto de equipo + 18 jugadores" },

  { section_id: "group_b_can",    section_name: "Grupo B — Canadá",               code_prefix: "CAN", from: 1, to: 20, count: 20, description: "Escudo + foto de equipo + 18 jugadores" },
  { section_id: "group_b_bih",    section_name: "Grupo B — Bosnia y Herzegovina", code_prefix: "BIH", from: 1, to: 20, count: 20, description: "Escudo + foto de equipo + 18 jugadores" },
  { section_id: "group_b_qat",    section_name: "Grupo B — Qatar",                code_prefix: "QAT", from: 1, to: 20, count: 20, description: "Escudo + foto de equipo + 18 jugadores" },
  { section_id: "group_b_sui",    section_name: "Grupo B — Suiza",                code_prefix: "SUI", from: 1, to: 20, count: 20, description: "Escudo + foto de equipo + 18 jugadores" },

  { section_id: "group_c_bra",    section_name: "Grupo C — Brasil",               code_prefix: "BRA", from: 1, to: 20, count: 20, description: "Escudo + foto de equipo + 18 jugadores" },
  { section_id: "group_c_mar",    section_name: "Grupo C — Marruecos",            code_prefix: "MAR", from: 1, to: 20, count: 20, description: "Escudo + foto de equipo + 18 jugadores" },
  { section_id: "group_c_hai",    section_name: "Grupo C — Haití",                code_prefix: "HAI", from: 1, to: 20, count: 20, description: "Escudo + foto de equipo + 18 jugadores" },
  { section_id: "group_c_sco",    section_name: "Grupo C — Escocia",              code_prefix: "SCO", from: 1, to: 20, count: 20, description: "Escudo + foto de equipo + 18 jugadores" },

  { section_id: "group_d_usa",    section_name: "Grupo D — Estados Unidos",       code_prefix: "USA", from: 1, to: 20, count: 20, description: "Escudo + foto de equipo + 18 jugadores" },
  { section_id: "group_d_par",    section_name: "Grupo D — Paraguay",             code_prefix: "PAR", from: 1, to: 20, count: 20, description: "Escudo + foto de equipo + 18 jugadores" },
  { section_id: "group_d_aus",    section_name: "Grupo D — Australia",            code_prefix: "AUS", from: 1, to: 20, count: 20, description: "Escudo + foto de equipo + 18 jugadores" },
  { section_id: "group_d_tur",    section_name: "Grupo D — Türkiye",              code_prefix: "TUR", from: 1, to: 20, count: 20, description: "Escudo + foto de equipo + 18 jugadores" },

  { section_id: "group_e_ger",    section_name: "Grupo E — Alemania",             code_prefix: "GER", from: 1, to: 20, count: 20, description: "Escudo + foto de equipo + 18 jugadores" },
  { section_id: "group_e_cuw",    section_name: "Grupo E — Curaçao",              code_prefix: "CUW", from: 1, to: 20, count: 20, description: "Escudo + foto de equipo + 18 jugadores" },
  { section_id: "group_e_civ",    section_name: "Grupo E — Costa de Marfil",      code_prefix: "CIV", from: 1, to: 20, count: 20, description: "Escudo + foto de equipo + 18 jugadores" },
  { section_id: "group_e_ecu",    section_name: "Grupo E — Ecuador",              code_prefix: "ECU", from: 1, to: 20, count: 20, description: "Escudo + foto de equipo + 18 jugadores" },

  { section_id: "group_f_ned",    section_name: "Grupo F — Países Bajos",         code_prefix: "NED", from: 1, to: 20, count: 20, description: "Escudo + foto de equipo + 18 jugadores" },
  { section_id: "group_f_jpn",    section_name: "Grupo F — Japón",                code_prefix: "JPN", from: 1, to: 20, count: 20, description: "Escudo + foto de equipo + 18 jugadores" },
  { section_id: "group_f_swe",    section_name: "Grupo F — Suecia",               code_prefix: "SWE", from: 1, to: 20, count: 20, description: "Escudo + foto de equipo + 18 jugadores" },
  { section_id: "group_f_tun",    section_name: "Grupo F — Túnez",                code_prefix: "TUN", from: 1, to: 20, count: 20, description: "Escudo + foto de equipo + 18 jugadores" },

  { section_id: "group_g_bel",    section_name: "Grupo G — Bélgica",              code_prefix: "BEL", from: 1, to: 20, count: 20, description: "Escudo + foto de equipo + 18 jugadores" },
  { section_id: "group_g_egy",    section_name: "Grupo G — Egipto",               code_prefix: "EGY", from: 1, to: 20, count: 20, description: "Escudo + foto de equipo + 18 jugadores" },
  { section_id: "group_g_irn",    section_name: "Grupo G — Irán",                 code_prefix: "IRN", from: 1, to: 20, count: 20, description: "Escudo + foto de equipo + 18 jugadores" },
  { section_id: "group_g_nzl",    section_name: "Grupo G — Nueva Zelanda",        code_prefix: "NZL", from: 1, to: 20, count: 20, description: "Escudo + foto de equipo + 18 jugadores" },

  { section_id: "group_h_esp",    section_name: "Grupo H — España",               code_prefix: "ESP", from: 1, to: 20, count: 20, description: "Escudo + foto de equipo + 18 jugadores" },
  { section_id: "group_h_cpv",    section_name: "Grupo H — Cabo Verde",           code_prefix: "CPV", from: 1, to: 20, count: 20, description: "Escudo + foto de equipo + 18 jugadores" },
  { section_id: "group_h_ksa",    section_name: "Grupo H — Arabia Saudita",       code_prefix: "KSA", from: 1, to: 20, count: 20, description: "Escudo + foto de equipo + 18 jugadores" },
  { section_id: "group_h_uru",    section_name: "Grupo H — Uruguay",              code_prefix: "URU", from: 1, to: 20, count: 20, description: "Escudo + foto de equipo + 18 jugadores" },

  { section_id: "group_i_fra",    section_name: "Grupo I — Francia",              code_prefix: "FRA", from: 1, to: 20, count: 20, description: "Escudo + foto de equipo + 18 jugadores" },
  { section_id: "group_i_sen",    section_name: "Grupo I — Senegal",              code_prefix: "SEN", from: 1, to: 20, count: 20, description: "Escudo + foto de equipo + 18 jugadores" },
  { section_id: "group_i_irq",    section_name: "Grupo I — Irak",                 code_prefix: "IRQ", from: 1, to: 20, count: 20, description: "Escudo + foto de equipo + 18 jugadores" },
  { section_id: "group_i_nor",    section_name: "Grupo I — Noruega",              code_prefix: "NOR", from: 1, to: 20, count: 20, description: "Escudo + foto de equipo + 18 jugadores" },

  { section_id: "group_j_arg",    section_name: "Grupo J — Argentina",            code_prefix: "ARG", from: 1, to: 20, count: 20, description: "Escudo + foto de equipo + 18 jugadores" },
  { section_id: "group_j_alg",    section_name: "Grupo J — Argelia",              code_prefix: "ALG", from: 1, to: 20, count: 20, description: "Escudo + foto de equipo + 18 jugadores" },
  { section_id: "group_j_aut",    section_name: "Grupo J — Austria",              code_prefix: "AUT", from: 1, to: 20, count: 20, description: "Escudo + foto de equipo + 18 jugadores" },
  { section_id: "group_j_jor",    section_name: "Grupo J — Jordania",             code_prefix: "JOR", from: 1, to: 20, count: 20, description: "Escudo + foto de equipo + 18 jugadores" },

  { section_id: "group_k_por",    section_name: "Grupo K — Portugal",             code_prefix: "POR", from: 1, to: 20, count: 20, description: "Escudo + foto de equipo + 18 jugadores" },
  { section_id: "group_k_cod",    section_name: "Grupo K — RD Congo",             code_prefix: "COD", from: 1, to: 20, count: 20, description: "Escudo + foto de equipo + 18 jugadores" },
  { section_id: "group_k_uzb",    section_name: "Grupo K — Uzbekistán",           code_prefix: "UZB", from: 1, to: 20, count: 20, description: "Escudo + foto de equipo + 18 jugadores" },
  { section_id: "group_k_col",    section_name: "Grupo K — Colombia",             code_prefix: "COL", from: 1, to: 20, count: 20, description: "Escudo + foto de equipo + 18 jugadores" },

  { section_id: "group_l_eng",    section_name: "Grupo L — Inglaterra",           code_prefix: "ENG", from: 1, to: 20, count: 20, description: "Escudo + foto de equipo + 18 jugadores" },
  { section_id: "group_l_cro",    section_name: "Grupo L — Croacia",              code_prefix: "CRO", from: 1, to: 20, count: 20, description: "Escudo + foto de equipo + 18 jugadores" },
  { section_id: "group_l_gha",    section_name: "Grupo L — Ghana",                code_prefix: "GHA", from: 1, to: 20, count: 20, description: "Escudo + foto de equipo + 18 jugadores" },
  { section_id: "group_l_pan",    section_name: "Grupo L — Panamá",               code_prefix: "PAN", from: 1, to: 20, count: 20, description: "Escudo + foto de equipo + 18 jugadores" },

  { section_id: "history",        section_name: "FIFA World Cup History",         code_prefix: "FWC", from: 9, to: 19, count: 11, description: "Campeones de mundiales pasados (1934–2022)" },
];

function _codeFor(section, n) {
  if (section.section_id === "panini") return "00";
  return `${section.code_prefix}${n}`;
}

function _build() {
  const stickers = [];
  const byCode = new Map();
  const bySection = new Map();

  for (const section of SECTIONS) {
    const list = [];
    for (let n = section.from; n <= section.to; n++) {
      const code = _codeFor(section, n);
      const sticker = Object.freeze({
        code,
        n,                                  // número impreso (puede repetirse entre prefijos)
        index: stickers.length + 1,         // 1..TOTAL_STICKERS, orden de álbum
        section_id: section.section_id,
        section_name: section.section_name,
        prefix: section.code_prefix,
      });
      if (byCode.has(code)) {
        throw new Error(`album-structure: código duplicado "${code}"`);
      }
      stickers.push(sticker);
      byCode.set(code, sticker);
      list.push(sticker);
    }
    bySection.set(section.section_id, list);
  }
  return { stickers, byCode, bySection };
}

const _built = _build();
export const STICKERS       = _built.stickers;       // [{code, n, index, section_id, section_name, prefix}, ...]
export const BY_CODE        = _built.byCode;         // Map: code → sticker
export const BY_SECTION     = _built.bySection;      // Map: section_id → sticker[]
export const TOTAL_STICKERS = STICKERS.length;       // 980

export function findByCode(input) {
  if (!input) return null;
  const code = String(input).trim().toUpperCase().replace(/\s+/g, "");
  return BY_CODE.get(code) || null;
}

// Etiqueta corta para mostrar dentro de la celda (sin prefijo cuando ya hay
// header de sección, salvo para "00" del panini).
export function shortLabel(sticker) {
  if (sticker.section_id === "panini") return "00";
  return String(sticker.n);
}
