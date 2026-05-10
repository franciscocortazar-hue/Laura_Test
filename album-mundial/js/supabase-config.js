// Pega aquí los datos de tu proyecto Supabase (Project Settings > API).
// Mientras no los pegues, la app corre en MODO DEMO usando localStorage.
//
// El "anon key" es público — se expone en el cliente y es seguro. La protección
// real está en las políticas de Row-Level Security (ver supabase-schema.sql).

export const supabaseConfig = {
  url: "PASTE_HERE",          // ej. "https://abcd1234.supabase.co"
  anonKey: "PASTE_HERE",      // tu anon/public key
};

// Total de láminas del álbum Panini Mundial 2026 (incluye especiales).
export const TOTAL_STICKERS = 980;

export const isSupabaseConfigured = () =>
  !!supabaseConfig.url &&
  !supabaseConfig.url.startsWith("PASTE") &&
  !!supabaseConfig.anonKey &&
  !supabaseConfig.anonKey.startsWith("PASTE");
