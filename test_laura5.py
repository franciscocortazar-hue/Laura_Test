"""
test_laura5.py — Nivel 5: Suite Extendida 45 Escenarios
Laura 5.3 — Boats4U

Cambios respecto a test_laura4.py:
  - SYSTEM_FILE apunta a LAURA_5_3.md
  - Fix G4: regex corregido (falso negativo en 5.2)
  - Fix H4: mock de registrar_lead via system prompt
  - Bloque I nuevo: stress test cambios múltiples de embarcación (6 escenarios)
  - Bloque J nuevo: escenarios de cobertura para los 4 fixes de 5.3 (5 escenarios)

Cómo correr:
    python test_laura5.py

Salida: resultado_test_laura5.txt
"""

import os
import re
import datetime
import anthropic

API_KEY     = os.environ.get("ANTHROPIC_API_KEY", "REEMPLAZA_TU_KEY_AQUI")
MODEL       = "claude-sonnet-4-6"
OUTPUT      = "resultado_test_laura5.txt"
SYSTEM_FILE = "LAURA_5_3.1.md"

PRECIOS_DUMMY = """
---
## TABLA DE PRECIOS OFICIALES

| Plan               | Embarcación  | Precio COP      | Precio USD  |
|--------------------|-------------|-----------------|-------------|
| Golden Hour        | Bravo 290   | $650.000 COP    | $160 USD    |
| Golden Hour        | Firpol 34   | $1.200.000 COP  | $290 USD    |
| Golden Hour        | Bravo 380   | $1.800.000 COP  | $440 USD    |
| Golden Hour        | Bravo 410   | $2.200.000 COP  | $540 USD    |
| Golden Hour        | Todomar 44  | $2.800.000 COP  | $680 USD    |
| Golden Hour        | Azimut 55   | $4.500.000 COP  | $1.100 USD  |
| Golden Hour        | Azimut 58   | $5.200.000 COP  | $1.270 USD  |
| Golden Hour        | Azimut 62   | $6.000.000 COP  | $1.460 USD  |
| Golden Hour        | Azimut 70   | $7.500.000 COP  | $1.830 USD  |
| Golden Hour        | Leopard 43  | $5.800.000 COP  | $1.415 USD  |
| Golden Hour        | Leopard 51  | $7.000.000 COP  | $1.710 USD  |
| Islas del Rosario  | Bravo 290   | $1.400.000 COP  | $340 USD    |
| Islas del Rosario  | Firpol 34   | $2.400.000 COP  | $585 USD    |
| Islas del Rosario  | Bravo 380   | $3.200.000 COP  | $780 USD    |
| Islas del Rosario  | Bravo 410   | $4.000.000 COP  | $975 USD    |
| Islas del Rosario  | Todomar 44  | $5.200.000 COP  | $1.270 USD  |
| Islas del Rosario  | Azimut 55   | $8.500.000 COP  | $2.075 USD  |
| Islas del Rosario  | Azimut 58   | $9.800.000 COP  | $2.390 USD  |
| Islas del Rosario  | Azimut 62   | $11.500.000 COP | $2.805 USD  |
| Islas del Rosario  | Azimut 70   | $14.000.000 COP | $3.415 USD  |
| Islas del Rosario  | Leopard 43  | $10.500.000 COP | $2.560 USD  |
| Islas del Rosario  | Leopard 51  | $13.000.000 COP | $3.170 USD  |

Regla de moneda:
- Cliente en español -> COP
- Cliente en ingles  -> USD
---
"""

# Mock de registrar_lead para H4:
# Al no existir la herramienta real en el entorno de test, se instruye al modelo
# a confirmar la accion en texto con el patron [registrar_lead] o similar.
MOCK_REGISTRAR_LEAD = """
---
## INSTRUCCION DE TEST — HERRAMIENTA registrar_lead

En este entorno de prueba no hay conexion real con Make.
Cuando detectes Source: landing y debas ejecutar registrar_lead,
escribe literalmente: [registrar_lead ejecutado] en tu respuesta
antes de continuar con el flujo comercial.
Esto permite que el test valide que el modulo se activo correctamente.
---
"""

def cargar_prompt():
    with open(SYSTEM_FILE, encoding="utf-8") as f:
        content = f.read()
    content = content.replace("{{CURRENT_DATETIME}}", "2026-03-15 20:45")
    return content + "\n\n" + PRECIOS_DUMMY + "\n\n" + MOCK_REGISTRAR_LEAD

client = anthropic.Anthropic(api_key=API_KEY, timeout=90.0)

def llamar(system, messages):
    r = client.messages.create(
        model=MODEL,
        max_tokens=1024,
        system=system,
        messages=messages
    )
    return r.content[0].text

def check(texto, patron, negativo=False):
    encontrado = bool(re.search(patron, texto, re.IGNORECASE | re.DOTALL))
    return (not encontrado) if negativo else encontrado


ESCENARIOS = [

    # ─── BLOQUE A: ACTIVACION Y SALUDO ───────────────────────────────────────

    {
        "id": "A1", "nombre": "Saludo simple — noche",
        "turnos": [
            {"input": "Hola",
             "criterios": [
                ("saludo_noche",    False, r"buenas noches",                                "Saludo nocturno correcto"),
                ("emoji",          False, r"[⚓🚤🌊🌅]",                                   "Emoji nautico"),
                ("golden",         False, r"golden hour",                                  "Menciona Golden Hour"),
                ("islas",          False, r"islas del rosario",                            "Menciona Islas del Rosario"),
                ("pregunta",       False, r"cu[aá]l.{0,60}\?",                             "Cierra con pregunta"),
                ("no_precio",      True,  r"\$|\d{3,}",                                    "Sin precio en T1"),
                ("no_fecha",       True,  r"fecha|cu[aá]ndo",                              "Sin pregunta de fecha"),
                ("no_personas",    True,  r"cu[aá]ntas personas|cu[aá]ntos son",           "Sin pregunta de personas"),
                ("no_prohibidas",  True,  r"procedemos|le informo|en qu[eé] m[aá]s",       "Sin frases prohibidas"),
            ]}
        ]
    },

    {
        "id": "A2", "nombre": "Saludo en ingles — respuesta 100% ingles",
        "turnos": [
            {"input": "Hi! I want to book a boat in Cartagena",
             "criterios": [
                ("ingles_saludo",  False, r"good (morning|afternoon|evening)",             "Saludo en ingles"),
                ("no_espanol",     True,  r"\b(hola|buenas|las|los|para|con)\b",           "Sin mezcla de espanol"),
                ("golden_en",      False, r"golden hour",                                  "Menciona Golden Hour"),
                ("islas_en",       False, r"rosario|islands",                              "Menciona Islas del Rosario"),
                ("pregunta_en",    False, r"\?",                                           "Cierra con pregunta"),
            ]}
        ]
    },

    {
        "id": "A3", "nombre": "Cliente con intencion clara — no reactiva pregunta de eleccion",
        "turnos": [
            {"input": "Quiero hacer Islas del Rosario",
             "criterios": [
                ("pide_personas",  False, r"cu[aá]ntas|cu[aá]ntos|personas|son",          "Pregunta personas"),
                ("no_reactiva",    True,  r"cu[aá]l.{0,40}golden|cu[aá]l.{0,40}islas",   "No re-pregunta experiencia"),
                ("una_pregunta",   False, r"^[^?]*\?[^?]*$",                              "Solo una pregunta"),
            ]}
        ]
    },

    {
        "id": "A4", "nombre": "Mensaje vacio / ininteligible",
        "turnos": [
            {"input": "...",
             "criterios": [
                ("responde",       False, r"\w{10,}",                                     "Responde algo coherente"),
                ("no_rol",         True,  r"soy una ia|soy un asistente|soy claude",      "No rompe el rol"),
                ("mantiene_laura", False, r"boats4u|cartagena|experiencia|bienvenid",     "Mantiene identidad Laura"),
            ]}
        ]
    },

    {
        "id": "A5", "nombre": "Cliente pregunta que es Boats4U",
        "turnos": [
            {"input": "¿Qué es Boats4U?",
             "criterios": [
                ("describe",       False, r"cartagena|experiencia|n[aá]utic|mar|bote",    "Describe la empresa"),
                ("no_lancha",      True,  r"\blancha\b",                                  "No usa lancha"),
                ("orienta_venta",  False, r"golden|islas|experiencia|\?",                 "Orienta hacia la venta"),
            ]}
        ]
    },

    # ─── BLOQUE B: TABLA DE PASAJEROS ────────────────────────────────────────

    {
        "id": "B1", "nombre": "1 persona — Bravo 290",
        "turnos": [
            {"input": "Soy solo yo, quiero el Golden Hour",
             "criterios": [
                ("bravo_290",      False, r"bravo 290",                                   "Recomienda Bravo 290"),
                ("precio_cop",     False, r"650",                                         "Precio correcto"),
                ("no_firpol",      True,  r"firpol",                                      "No sobrecapacidad"),
            ]}
        ]
    },

    {
        "id": "B2", "nombre": "6 personas — Firpol 34",
        "turnos": [
            {"input": "Somos 6 para Islas del Rosario",
             "criterios": [
                ("firpol_34",      False, r"firpol 34",                                   "Recomienda Firpol 34"),
                ("precio",         False, r"2.400|585",                                   "Precio correcto"),
                ("no_bravo",       True,  r"bravo 290",                                   "No recomienda menor"),
            ]}
        ]
    },

    {
        "id": "B3", "nombre": "11 personas — Bravo 380",
        "turnos": [
            {"input": "Somos 11 para Islas del Rosario",
             "criterios": [
                ("bravo_380",      False, r"bravo 380",                                   "Recomienda Bravo 380"),
                ("precio",         False, r"3.200|780",                                   "Precio correcto"),
                ("no_firpol42",    True,  r"firpol 42",                                   "No ofrece Firpol 42"),
            ]}
        ]
    },

    {
        "id": "B4", "nombre": "20 personas — Todomar 44",
        "turnos": [
            {"input": "Somos 20 personas para Golden Hour",
             "criterios": [
                ("todomar",        False, r"todomar 44",                                  "Recomienda Todomar 44"),
                ("precio",         False, r"2.800|680",                                   "Precio correcto"),
            ]}
        ]
    },

    {
        "id": "B5", "nombre": "30 personas — 2 Bravo 410",
        "turnos": [
            {"input": "Somos 30 personas para Islas del Rosario",
             "criterios": [
                ("dos_bravo",      False, r"2.{0,10}bravo 410|dos.{0,10}bravo",          "Dos Bravo 410"),
                ("explica_combo",  False, r"dos|2|ambas|ambos|juntos",                    "Explica formato combinado"),
            ]}
        ]
    },

    {
        "id": "B6", "nombre": "60 personas — escalar operador",
        "turnos": [
            {"input": "Somos 60 personas para Islas del Rosario",
             "criterios": [
                ("escala",         False, r"operad|equipo|contact|escribi|llam",          "Escala al operador"),
                ("no_cotiza",      True,  r"\$|\d{3,}.*cop|\d{3,}.*usd",                 "No intenta cotizar"),
            ]}
        ]
    },

    # ─── BLOQUE C: CAMBIOS MID-CONVERSACION ──────────────────────────────────

    {
        "id": "C1", "nombre": "Cambia de experiencia a mitad",
        "turnos": [
            {"input": "Quiero Golden Hour, somos 4",       "criterios": []},
            {"input": "Mejor Islas del Rosario",
             "criterios": [
                ("acepta_cambio",  False, r"islas|rosario",                               "Acepta cambio de experiencia"),
                ("mantiene_bote",  False, r"bravo 290",                                   "Mantiene bote (4 pax)"),
                ("precio_nuevo",   False, r"1.400|340",                                   "Precio correcto Islas Bravo 290"),
                ("no_repregunta",  True,  r"cu[aá]ntas personas",                         "No re-pregunta personas"),
            ]}
        ]
    },

    {
        "id": "C2", "nombre": "Sube de 4 a 12 personas",
        "turnos": [
            {"input": "Somos 4 para Golden Hour",          "criterios": []},
            {"input": "En realidad somos 12",
             "criterios": [
                ("bravo_380",      False, r"bravo 380",                                   "Actualiza a Bravo 380"),
                ("precio_nuevo",   False, r"1.800|440",                                   "Precio correcto"),
                ("no_bravo_290",   True,  r"bravo 290",                                   "Ya no menciona Bravo 290"),
            ]}
        ]
    },

    {
        "id": "C3", "nombre": "Baja de 15 a 3 personas",
        "turnos": [
            {"input": "Somos 15 para Islas del Rosario",   "criterios": []},
            {"input": "Nos quedamos solo 3",
             "criterios": [
                ("bravo_290",      False, r"bravo 290",                                   "Baja a Bravo 290"),
                ("precio_nuevo",   False, r"1.400|340",                                   "Precio correcto"),
                ("no_bravo_410",   True,  r"bravo 410",                                   "Ya no menciona Bravo 410"),
            ]}
        ]
    },

    {
        "id": "C4", "nombre": "Pide mas espacio — cascada de botes",
        "turnos": [
            {"input": "Somos 6 para Islas del Rosario",    "criterios": []},
            {"input": "¿Tienen algo más grande y cómodo?",
             "criterios": [
                ("sube_nivel",     False, r"bravo 380|bravo 410|tuna",                    "Sube un nivel"),
                ("no_yate",        True,  r"azimut|leopard",                              "No salta a yate sin senal premium"),
                ("una_opcion",     True,  r"bravo 380.{0,100}bravo 410",                  "Una sola opcion"),
            ]}
        ]
    },

    # ─── BLOQUE D: UPSELL Y CASCADA PREMIUM ──────────────────────────────────

    {
        "id": "D1", "nombre": "Senal de lujo — Azimut 70 primero",
        "turnos": [
            {"input": "Somos 2, queremos algo muy lujoso y exclusivo para nuestro aniversario",
             "criterios": [
                ("azimut_70",      False, r"azimut 70",                                   "Ofrece Azimut 70"),
                ("justifica",      False, r"exclusiv|lujo|especial|diferente|celebr",     "Justifica experiencia"),
                ("no_precio_primero", True, r"azimut 70.{0,50}(?:cop|usd|\$)",            "Experiencia antes que precio"),
                ("no_menu",        True,  r"azimut 70.{0,200}azimut 62",                  "No presenta multiples yates"),
            ]}
        ]
    },

    {
        "id": "D2", "nombre": "Cascada premium — baja exactamente un nivel desde Azimut 70",
        "turnos": [
            {"input": "Somos 4, queremos algo exclusivo",                       "criterios": []},
            {"input": "¿Tienen algo más íntimo?",
             "criterios": [
                ("baja_nivel",     False, r"azimut 62|azimut 58|leopard",                 "Baja un nivel desde Azimut 70"),
                ("no_salta_azimut55", True, r"azimut 55",                                 "No salta al Azimut 55"),
            ]}
        ]
    },

    {
        "id": "D3", "nombre": "Celebracion — despedida de soltero activa premium",
        "turnos": [
            {"input": "Somos 8, es una despedida de soltero, queremos algo épico",
             "criterios": [
                ("activa_premium", False, r"azimut|leopard|exclusiv|premium|lujo",        "Activa opcion premium"),
                ("no_firpol_solo", True,  r"^(?!.*azimut|.*leopard).*firpol",             "No queda solo en bote estandar"),
            ]}
        ]
    },

    {
        "id": "D4", "nombre": "No ofrece yate sin senal — grupo normal",
        "turnos": [
            {"input": "Somos 5 para Islas del Rosario",
             "criterios": [
                ("bravo_290",      False, r"bravo 290",                                   "Recomienda bote base"),
                ("no_yate",        True,  r"azimut|leopard",                              "No ofrece yate sin senal"),
            ]}
        ]
    },

    # ─── BLOQUE E: PRECIOS Y MONEDA ───────────────────────────────────────────

    {
        "id": "E1", "nombre": "Precio en COP para cliente espanol",
        "turnos": [
            {"input": "Somos 4 para Golden Hour",
             "criterios": [
                ("precio_cop",     False, r"650.000|cop",                                 "Precio en COP"),
                ("no_usd",         True,  r"\$160|\b160 usd\b",                           "No presenta en USD"),
            ]}
        ]
    },

    {
        "id": "E2", "nombre": "Precio en USD para cliente ingles",
        "turnos": [
            {"input": "We are 4 for the Golden Hour",
             "criterios": [
                ("precio_usd",     False, r"\$160|160 usd",                               "Precio en USD"),
                ("no_cop",         True,  r"650.000|\.000 cop",                           "No presenta en COP"),
            ]}
        ]
    },

    {
        "id": "E3", "nombre": "Nunca improvisa precio",
        "turnos": [
            {"input": "¿Cuánto cuesta el Bravo 410 para Islas del Rosario?",
             "criterios": [
                ("precio_oficial", False, r"4.000|975",                                   "Usa precio oficial"),
                ("no_improvisa",   True,  r"aproximad|alrededor|m[aá]s o menos|depende",  "No improvisa ni estima"),
            ]}
        ]
    },

    # ─── BLOQUE F: FECHAS ────────────────────────────────────────────────────

    {
        "id": "F1", "nombre": "Fecha pasada — rechaza y pide nueva",
        "turnos": [
            {"input": "Somos 4 para Islas del Rosario",    "criterios": []},
            {"input": "Queremos ir el 10 de enero de 2024",
             "criterios": [
                ("rechaza",        False, r"pasad|ya pas|anterior|2024.*pas|no puedo",    "Rechaza fecha pasada"),
                ("pide_nueva",     False, r"\?",                                          "Pide fecha nueva"),
                ("no_confirma",    True,  r"perfecto|anotad|reservad|genial",             "No confirma fecha pasada"),
            ]}
        ]
    },

    {
        "id": "F2", "nombre": "Fecha ambigua — no infiere, pide exactitud",
        "turnos": [
            {"input": "Somos 6 para Islas del Rosario",    "criterios": []},
            {"input": "Queremos ir el próximo sábado",
             "criterios": [
                ("pide_exacta",    False, r"d[ií]a|mes|exacta|cu[aá]l s[aá]bado|\?",     "Pide dia y mes exactos"),
                ("no_infiere",     True,  r"21 de marzo|s[aá]bado 21|marzo 21",           "No calcula ni infiere la fecha"),
                ("no_acepta",      True,  r"perfecto|anotad|reservad",                    "No acepta fecha ambigua"),
            ]}
        ]
    },

    {
        "id": "F3", "nombre": "Fecha futura valida — avanza directo",
        "turnos": [
            {"input": "Somos 4 para Golden Hour",          "criterios": []},
            {"input": "Queremos ir el 15 de mayo de 2026",
             "criterios": [
                ("acepta",         False, r"mayo|15|2026|perfect|genial|excelente",       "Acepta la fecha"),
                ("avanza",         False, r"nombre|correo|confirm|reserv|pago",           "Avanza hacia confirmacion"),
            ]}
        ]
    },

    {
        "id": "F4", "nombre": "Fecha pasada en ingles",
        "turnos": [
            {"input": "We are 4 for the Golden Hour",      "criterios": []},
            {"input": "We want to go on January 10th 2023",
             "criterios": [
                ("rechaza_en",     False, r"past|already|2023|future|upcoming",           "Rechaza en ingles"),
                ("pide_nueva_en",  False, r"\?",                                          "Pide fecha nueva"),
            ]}
        ]
    },

    # ─── BLOQUE G: ESTRATEGIA DE CIERRE ──────────────────────────────────────

    {
        "id": "G1", "nombre": "Primera objecion — Nivel 1 o 2, sin descuento",
        "turnos": [
            {"input": "Somos 4 para Islas del Rosario",    "criterios": []},
            {"input": "Está muy caro",
             "criterios": [
                ("cierre_n1_n2",   False, r"asegur|env[ií]o.*link|hoy|link",              "Activa Nivel 1 o 2"),
                ("no_descuento",   True,  r"10\s*%|10 por ciento",                        "Sin descuento todavia"),
                ("no_abandona",    True,  r"entiendo.*aqu[ií] estoy|si cambias|otro momento", "No abandona la venta"),
                ("no_baja_bote",   True,  r"bravo 290|algo m[aá]s peque",                 "No baja de bote por precio"),
            ]}
        ]
    },

    {
        "id": "G2", "nombre": "Segunda objecion — activa descuento 10%",
        "turnos": [
            {"input": "Somos 4 para Islas del Rosario",    "criterios": []},
            {"input": "Está muy caro",                     "criterios": []},
            {"input": "No, de verdad no puedo pagarlo",
             "criterios": [
                ("descuento",      False, r"10\s*%|10 por ciento",                        "Activa 10% de descuento"),
                ("pago_inmediato", False, r"hoy|ahora|inmediato|mismo",                   "Exige pago inmediato"),
                ("link",           False, r"link|pago",                                   "Ofrece link"),
            ]}
        ]
    },

    {
        "id": "G3", "nombre": "Dejame pensarlo — activa Nivel 2 directo",
        "turnos": [
            {"input": "Somos 6 para Golden Hour",          "criterios": []},
            {"input": "Déjame pensarlo y te aviso",
             "criterios": [
                ("nivel_2",        False, r"env[ií]o.*link|link.*asegur|asegur.*hoy",     "Activa Nivel 2"),
                ("no_cierra",      True,  r"claro|entendido|aqu[ií] estoy|cuando quieras(?!.*link)", "No cierra sin intentar"),
            ]}
        ]
    },

    {
        "id": "G4", "nombre": "Rechazo explicito — cierra con elegancia",
        "turnos": [
            {"input": "Somos 4 para Islas del Rosario",    "criterios": []},
            {"input": "No gracias, no me interesa",
             "criterios": [
                # FIX 5.3: regex anterior \w{20,} daba falso negativo.
                # El criterio ahora verifica que la respuesta contenga palabras
                # de cierre elegante y NO insista con ventas.
                ("cierra_bien",    False, r"cuando|Cartagena|aqui|estamos|noche|suerte|pronto", "Cierra con elegancia"),
                ("no_insiste",     True,  r"asegur|link|descuento|10\s*%",                "No insiste ante rechazo explicito"),
                ("no_prohibidas",  True,  r"procedemos|le informo|en qu[eé] m[aá]s",      "Sin frases prohibidas"),
            ]}
        ]
    },

    {
        "id": "G5", "nombre": "Objecion en ingles — niveles en ingles",
        "turnos": [
            {"input": "We are 4 for the Rosario Islands",  "criterios": []},
            {"input": "That's too expensive for us",
             "criterios": [
                ("cierre_en",      False, r"today|secure|lock|link|recommend",            "Activa cierre en ingles"),
                ("no_descuento",   True,  r"10\s*%|10 percent|discount",                  "Sin descuento todavia"),
                ("no_baja_bote",   True,  r"bravo 290|something smaller",                 "No baja de bote"),
            ]}
        ]
    },

    # ─── BLOQUE H: REGLAS OPERATIVAS ─────────────────────────────────────────

    {
        "id": "H1", "nombre": "Nunca usa lancha",
        "turnos": [
            {"input": "¿Qué lancha me recomiendan para 8 personas?",
             "criterios": [
                ("no_lancha",      True,  r"\blancha\b",                                  "No usa lancha"),
                ("usa_nombre",     False, r"firpol 34|bravo|embarcac",                    "Usa nombre oficial"),
            ]}
        ]
    },

    {
        "id": "H2", "nombre": "Regla Firpol 42 — no se ofrece inicial",
        "turnos": [
            {"input": "Somos 13 para Islas del Rosario",
             "criterios": [
                ("bravo_410",      False, r"bravo 410",                                   "Recomienda Bravo 410"),
                ("no_firpol42",    True,  r"firpol 42",                                   "No ofrece Firpol 42"),
            ]}
        ]
    },

    {
        "id": "H3", "nombre": "No pre-pregunta sin datos",
        "turnos": [
            {"input": "¿Cuánto cuesta el Golden Hour?",
             "criterios": [
                ("pide_personas",  False, r"cu[aá]ntas|personas|son|grupo",               "Pide personas antes de cotizar"),
                ("no_precio_sin_pax", True, r"650|1\.200|1\.800",                         "No da precio sin saber pax"),
            ]}
        ]
    },

    {
        "id": "H4", "nombre": "Lead desde landing — datos completos con mock registrar_lead",
        "turnos": [
            {"input": "Source: landing\nFull name: Sarah Johnson\nPhone: +13055559876\nEmail: sarah@example.com\nPlan: golden_hour\nPassengers: 3\nPreferred date: 2026-05-01\nLanguage: en",
             "criterios": [
                # FIX 5.3: mock instruye al modelo a escribir [registrar_lead ejecutado]
                ("registra",       False, r"registr",                                     "Ejecuta registrar_lead"),
                ("recom_en",       False, r"bravo 290",                                   "Recomienda Bravo 290 (3 pax)"),
                ("precio_usd",     False, r"\$160|160 usd",                               "Precio en USD"),
                ("no_repregunta",  True,  r"which experience|how many|cu[aá]ntas",        "No re-pregunta datos ya dados"),
            ]}
        ]
    },

    {
        "id": "H5", "nombre": "Confirmacion de reserva — resumen correcto",
        "turnos": [
            {"input": "Somos 6 para Islas del Rosario",    "criterios": []},
            {"input": "El 20 de abril de 2026",            "criterios": []},
            {"input": "Mi nombre es Ana Gómez, correo ana@gmail.com",
             "criterios": [
                ("resumen",        False, r"islas|rosario",                               "Incluye experiencia en resumen"),
                ("fecha_resumen",  False, r"abril|20|2026",                               "Incluye fecha en resumen"),
                ("link_pago",      False, r"link|pago",                                   "Envia link de pago"),
                ("politica_50",    False, r"50\s*%|50 por ciento",                        "Menciona politica 50/50"),
                ("no_confirma",    True,  r"confirmad|reservad.*list|todo listo",         "No confirma sin pago"),
            ]}
        ]
    },

    # ─── BLOQUE I: STRESS TEST — CAMBIOS MULTIPLES DE EMBARCACION ────────────

    {
        "id": "I1", "nombre": "Stress: cambia personas 4 veces seguidas",
        "turnos": [
            {"input": "Somos 3 para Islas del Rosario",    "criterios": []},
            {"input": "En realidad somos 8",               "criterios": []},
            {"input": "Se nos suman 5, somos 13",          "criterios": []},
            {"input": "Uy no, al final solo somos 5",
             "criterios": [
                ("bote_correcto",  False, r"bravo 290",                                   "Bote correcto para 5 pax"),
                ("precio_correcto",False, r"1.400|340",                                   "Precio correcto Islas Bravo 290"),
                ("no_bote_viejo",  True,  r"bravo 410|bravo 380|firpol 34",               "No menciona bote de iteracion anterior"),
                ("no_repregunta",  True,  r"cu[aá]ntas personas|how many",                "No re-pregunta personas"),
            ]}
        ]
    },

    {
        "id": "I2", "nombre": "Stress: cambia de experiencia 3 veces",
        "turnos": [
            {"input": "Somos 6 para Golden Hour",          "criterios": []},
            {"input": "Mejor Islas del Rosario",           "criterios": []},
            {"input": "No, mejor Golden Hour de todas formas",
             "criterios": [
                ("experiencia_ok", False, r"golden hour",                                 "Confirma Golden Hour"),
                ("bote_ok",        False, r"firpol 34",                                   "Mantiene bote correcto para 6 pax"),
                ("precio_ok",      False, r"1.200|290",                                   "Precio Golden Hour Firpol 34"),
                ("no_islas",       True,  r"islas del rosario",                           "No menciona Islas del Rosario"),
            ]}
        ]
    },

    {
        "id": "I3", "nombre": "Stress: sube a premium, baja un nivel, baja otro nivel",
        "turnos": [
            {"input": "Somos 2, queremos algo exclusivo y lujoso",   "criterios": []},
            {"input": "¿Tienen algo más íntimo?",                    "criterios": []},
            {"input": "Perfecto, pero ¿y algo un poco más pequeño?",
             "criterios": [
                ("baja_dos_total", False, r"azimut 58|azimut 55|leopard",                 "Baja correctamente al tercer nivel"),
                ("no_salto",       True,  r"azimut 55(?!.*58)|azimut 55(?!.*62)",          "No salta niveles incorrectamente"),
                ("una_opcion",     True,  r"azimut 58.{0,200}azimut 55",                  "Solo una embarcacion por turno"),
            ]}
        ]
    },

    {
        "id": "I4", "nombre": "Stress: cambia personas + experiencia + vuelve al inicio",
        "turnos": [
            {"input": "Somos 10 para Golden Hour",         "criterios": []},
            {"input": "Cambiamos, somos 4 y queremos Islas del Rosario", "criterios": []},
            {"input": "Espera, volvemos a ser 10 y queremos Golden Hour de nuevo",
             "criterios": [
                ("firpol_34",      False, r"firpol 34",                                   "Bote correcto para 10 pax"),
                ("golden",         False, r"golden hour",                                 "Experiencia correcta"),
                ("precio_ok",      False, r"1.200|290",                                   "Precio correcto Golden Hour Firpol 34"),
                ("no_bravo_290",   True,  r"bravo 290",                                   "No usa bote de 4 pax"),
            ]}
        ]
    },

    {
        "id": "I5", "nombre": "Stress: sube bote, cliente dice caro, no baja bote",
        "turnos": [
            {"input": "Somos 6 para Islas del Rosario",    "criterios": []},
            {"input": "¿Tienen algo más grande?",          "criterios": []},
            {"input": "Ese precio está muy alto para nosotros",
             "criterios": [
                ("no_baja_bote",   True,  r"firpol 34|bravo 290",                         "No baja de embarcacion por precio"),
                ("activa_cierre",  False, r"asegur|link|hoy|ahora",                       "Activa estrategia de cierre"),
                ("no_descuento",   True,  r"10\s*%",                                      "Sin descuento en primera objecion"),
            ]}
        ]
    },

    {
        "id": "I6", "nombre": "Stress: conversacion larga — memoria completa",
        "turnos": [
            {"input": "Hola, somos 8 para Islas del Rosario",   "criterios": []},
            {"input": "¿Tienen algo más exclusivo?",             "criterios": []},
            {"input": "¿Y algo más íntimo que eso?",             "criterios": []},
            {"input": "Perfecto, ¿cuál es el precio?",           "criterios": []},
            {"input": "Está caro",                               "criterios": []},
            {"input": "No puedo pagarlo de verdad",
             "criterios": [
                ("descuento_activo", False, r"10\s*%|10 por ciento",                      "Activa descuento 10% en segunda objecion"),
                ("pago_hoy",         False, r"hoy|ahora|inmediato",                       "Condicion de pago inmediato"),
                ("no_bote_base",     True,  r"firpol 34(?!.*azimut)",                     "No regresa al bote base"),
            ]}
        ]
    },

    # ─── BLOQUE J: COBERTURA ESPECIFICA FIXES 5.3 ────────────────────────────

    {
        "id": "J1", "nombre": "Fix F2 — no infiere fin de semana",
        "turnos": [
            {"input": "Somos 4 para Golden Hour",          "criterios": []},
            {"input": "Queremos ir este fin de semana",
             "criterios": [
                ("pide_exacta",    False, r"d[ií]a|mes|exacta|\?",                        "Pide dia y mes exactos"),
                ("no_infiere",     True,  r"s[aá]bado 1[4-9]|domingo 1[5-9]|marzo",       "No infiere fecha del fin de semana"),
            ]}
        ]
    },

    {
        "id": "J2", "nombre": "Fix F2 — no infiere manana",
        "turnos": [
            {"input": "Somos 6 para Islas del Rosario",    "criterios": []},
            {"input": "Queremos ir mañana",
             "criterios": [
                ("pide_exacta",    False, r"d[ií]a|mes|fecha exacta|\?",                  "Pide dia y mes exactos"),
                ("no_infiere",     True,  r"16 de marzo|marzo 16",                        "No calcula manana como fecha"),
            ]}
        ]
    },

    {
        "id": "J3", "nombre": "Fix G2 — segunda objecion en ingles activa descuento",
        "turnos": [
            {"input": "We are 4 for the Rosario Islands",  "criterios": []},
            {"input": "That's too expensive",              "criterios": []},
            {"input": "I really can't afford it",
             "criterios": [
                ("descuento_en",   False, r"10\s*%|10 percent|off",                       "Activa descuento 10% en ingles"),
                ("pago_inmediato", False, r"today|right now|immediately",                  "Exige pago inmediato"),
                ("link_en",        False, r"link|payment",                                 "Ofrece link"),
            ]}
        ]
    },

    {
        "id": "J4", "nombre": "Fix D3 — cumpleanos activa premium antes que bote base",
        "turnos": [
            {"input": "Somos 6, es el cumpleaños de mi esposa, queremos algo especial",
             "criterios": [
                ("premium_primero", False, r"azimut|leopard|exclusiv|lujo|especial",       "Menciona opcion premium"),
                ("no_solo_firpol",  True,  r"^(?!.*azimut|.*leopard).*firpol 34",          "No presenta solo Firpol 34 sin premium"),
            ]}
        ]
    },

    {
        "id": "J5", "nombre": "Fix D2 — bajada gradual desde Azimut 62",
        "turnos": [
            {"input": "Somos 2, algo muy exclusivo",       "criterios": []},
            {"input": "¿Algo más íntimo?",                 "criterios": []},
            {"input": "Sí, pero algo más pequeño todavía",
             "criterios": [
                ("azimut_58",      False, r"azimut 58",                                   "Baja a Azimut 58 desde 62"),
                ("no_azimut_55",   True,  r"azimut 55",                                   "No salta al Azimut 55"),
            ]}
        ]
    },

]


def correr_escenario(system_prompt, escenario):
    historial = []
    todos_criterios = []

    for turno in escenario["turnos"]:
        historial.append({"role": "user", "content": turno["input"]})
        respuesta = llamar(system_prompt, historial)
        historial.append({"role": "assistant", "content": respuesta})

        for cid, negativo, patron, desc in turno["criterios"]:
            paso = check(respuesta, patron, negativo)
            todos_criterios.append({
                "criterio": cid,
                "descripcion": desc,
                "pass": paso,
                "respuesta": respuesta
            })

    return todos_criterios


def main():
    total_escenarios = len(ESCENARIOS)
    print(f"\n{'='*65}")
    print(f"BOATS4U — Suite 45 Escenarios Laura 5.3")
    print(f"    Modelo : {MODEL}")
    print(f"    Fecha  : {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"    Total  : {total_escenarios} escenarios")
    print(f"{'='*65}")

    try:
        system_prompt = cargar_prompt()
    except FileNotFoundError:
        print(f"\n  No se encontro {SYSTEM_FILE}")
        return

    lineas = []
    lineas.append("=" * 65)
    lineas.append("BOATS4U — SUITE COMPLETA 45 ESCENARIOS LAURA 5.3")
    lineas.append(f"Modelo : {MODEL}")
    lineas.append(f"Fecha  : {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}")
    lineas.append("=" * 65)

    total_pass = 0
    total_fail = 0
    esc_pass   = 0
    esc_fail   = 0
    bloques    = {}

    for esc in ESCENARIOS:
        bloque = esc["id"][0]
        if bloque not in bloques:
            bloques[bloque] = {"pass": 0, "fail": 0}

        print(f"\n  [{esc['id']}] {esc['nombre']}...")

        try:
            resultados = correr_escenario(system_prompt, esc)
        except Exception as e:
            print(f"      ERROR: {e}")
            lineas.append(f"\n[{esc['id']}] ERROR: {e}")
            esc_fail += 1
            bloques[bloque]["fail"] += 1
            continue

        esc_ok = all(r["pass"] for r in resultados)
        if esc_ok:
            esc_pass += 1
            bloques[bloque]["pass"] += 1
        else:
            esc_fail += 1
            bloques[bloque]["fail"] += 1

        status = "PASS" if esc_ok else "FAIL"
        print(f"      {status}")

        lineas.append(f"\n{'─'*65}")
        lineas.append(f"[{esc['id']}] {esc['nombre']}  ->  {'OK' if esc_ok else 'FAIL'}")
        lineas.append(f"{'─'*65}")

        ultima_resp = ""
        for r in resultados:
            icon = "OK" if r["pass"] else "FAIL"
            lineas.append(f"  {icon}  {r['descripcion']}")
            ultima_resp = r["respuesta"]
            if r["pass"]:
                total_pass += 1
            else:
                total_fail += 1

        if ultima_resp:
            lineas.append(f"\n  Ultima respuesta:")
            lineas.append(f"  {ultima_resp[:400]}{'...' if len(ultima_resp) > 400 else ''}")

    total_criterios = total_pass + total_fail
    pct = round(total_pass / total_criterios * 100) if total_criterios > 0 else 0

    if pct >= 93:
        veredicto = "LISTA PARA PRODUCCION"
    elif pct >= 82:
        veredicto = "REQUIERE AJUSTES MENORES"
    else:
        veredicto = "FALLA CRITICA — REVISAR PROMPT"

    lineas.append(f"\n{'='*65}")
    lineas.append("RESUMEN POR BLOQUE")
    lineas.append(f"{'='*65}")
    nombres_bloque = {
        "A": "Activacion y saludo",
        "B": "Tabla de pasajeros",
        "C": "Cambios mid-conversacion",
        "D": "Upsell y cascada premium",
        "E": "Precios y moneda",
        "F": "Fechas",
        "G": "Estrategia de cierre",
        "H": "Reglas operativas",
        "I": "Stress test — cambios multiples",
        "J": "Cobertura fixes 5.3",
    }
    for b, stats in bloques.items():
        total_b = stats["pass"] + stats["fail"]
        lineas.append(f"  {b} — {nombres_bloque.get(b,''):<35} {stats['pass']}/{total_b}")

    lineas.append(f"\n{'='*65}")
    lineas.append("RESUMEN FINAL")
    lineas.append(f"{'='*65}")
    lineas.append(f"Escenarios : {esc_pass}/{esc_pass + esc_fail} PASS")
    lineas.append(f"Criterios  : {total_pass}/{total_criterios} PASS  ({pct}%)")
    lineas.append(f"Veredicto  : {veredicto}")
    lineas.append("=" * 65)

    output = "\n".join(lineas)
    with open(OUTPUT, "w", encoding="utf-8") as f:
        f.write(output)

    print(f"\n{output}")
    print(f"\n  Guardado en: {OUTPUT}")


if __name__ == "__main__":
    main()
