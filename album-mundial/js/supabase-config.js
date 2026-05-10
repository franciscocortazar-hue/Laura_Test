// Credenciales del proyecto Supabase. El `anonKey` (publishable) es público —
// va en el cliente y es seguro. La protección real está en las políticas RLS
// (ver supabase-schema.sql, ya aplicadas en el proyecto).

export const supabaseConfig = {
  url: "https://fnmxsafsgggswysaemwj.supabase.co",
  anonKey: "sb_publishable_6COFKaj_bjVpr6xsT5TUEQ_9oEi_Ttt",
};

// Total de láminas del álbum Panini Mundial 2026 (incluye especiales).
export const TOTAL_STICKERS = 980;

export const isSupabaseConfigured = () =>
  !!supabaseConfig.url &&
  !supabaseConfig.url.startsWith("PASTE") &&
  !!supabaseConfig.anonKey &&
  !supabaseConfig.anonKey.startsWith("PASTE");
