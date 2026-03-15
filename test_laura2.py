"""
test_laura2.py — Nivel 2: Stress Test Riguroso
Laura 5.1 — Boats4U

Cómo correr:
    python test_laura2.py

Salida: resultado_test_laura2.txt con PASS/FAIL por criterio.
"""

import os
import re
import json
import datetime
import anthropic

API_KEY = os.environ.get("ANTHROPIC_API_KEY", "REEMPLAZA_TU_KEY_AQUI")
MODEL   = "claude-sonnet-4-6"
OUTPUT  = "resultado_test_laura2.txt"

SYSTEM_FILE = "LAURA_5_1.md"

def cargar_prompt():
    with open(SYSTEM_FILE, encoding="utf-8") as f:
        content = f.read()
    now = "2026-03-15 20:45"
    return content.replace("{{CURRENT_DATETIME}}", now)

client = anthropic.Anthropic(api_key=API_KEY)

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

    {
        "id": "A1",
        "nombre": "Saludo nocturno — franja correcta",
        "system_override": None,
        "turnos": [
            {
                "input": "Hola",
                "criterios": [
                    ("franja_noche",       False, r"buenas noches",                          "Usa 'buenas noches' (horario 20:45)"),
                    ("emoji_nautico",      False, r"[⚓🚤🌊🌅]",                             "Incluye 1 emoji náutico"),
                    ("golden_hour",        False, r"golden hour",                            "Menciona Golden Hour"),
                    ("islas_rosario",      False, r"islas del rosario",                      "Menciona Islas del Rosario"),
                    ("pregunta_eleccion",  False, r"cu[aá]l.{0,50}(golden|islas|\?)",        "Cierra con pregunta de elección"),
                    ("no_precio",          True,  r"\$|usd|cop|\d{3,}",                      "No menciona precios en T1"),
                    ("no_fecha",           True,  r"fecha|cu[aá]ndo|d[ií]a",                 "No pregunta fecha en T1"),
                    ("no_personas",        True,  r"cu[aá]ntas personas|cuántos son",        "No pregunta número de personas en T1"),
                    ("no_frases_prohibidas", True, r"procedemos|le informo|con gusto|claro que s[ií]|en qu[eé] m[aá]s", "Sin frases de call center"),
                    ("max_lineas",         False, r"^.{0,600}$",                             "Respuesta concisa (max ~600 chars)"),
                ],
                "guardar_respuesta": True
            }
        ]
    },

    {
        "id": "A2",
        "nombre": "Cliente bilingüe — responde en inglés",
        "turnos": [
            {
                "input": "Hi there! I want to book a boat experience in Cartagena",
                "criterios": [
                    ("responde_ingles",    False, r"\b(the|and|for|you|our|we|I)\b",         "Responde en inglés"),
                    ("no_espanol",         True,  r"\b(hola|buenas|las|los|para|con)\b",     "No mezcla con español"),
                    ("golden_ingles",      False, r"golden hour",                            "Menciona Golden Hour en inglés"),
                    ("islas_ingles",       False, r"rosario|islands",                        "Menciona Islas del Rosario en inglés"),
                    ("pregunta_cierre",    False, r"\?",                                     "Cierra con pregunta"),
                ],
                "guardar_respuesta": True
            }
        ]
    },

    {
        "id": "B1",
        "nombre": "Grupo 8 pax — intención clara desde inicio",
        "turnos": [
            {
                "input": "Somos 8 personas para Islas del Rosario",
                "criterios": [
                    ("firpol_34",          False, r"firpol 34",                              "Recomienda Firpol 34 (6-10 pax)"),
                    ("precio_presente",    False, r"\$|usd|cop|\d{3,}",                      "Presenta precio"),
                    ("pregunta_fecha",     False, r"fecha|cu[aá]ndo|d[ií]a",                 "Pregunta por fecha"),
                    ("no_reactiva",        True,  r"cu[aá]l.{0,30}(golden|islas).*\?",       "No re-pregunta la experiencia"),
                    ("no_menu",            True,  r"(bravo|tuna|todomar).{0,20}(bravo|tuna|todomar)", "No presenta múltiples botes"),
                    ("una_pregunta",       False, r"^[^?]*\?[^?]*$",                         "Solo una pregunta en el mensaje"),
                ],
                "guardar_respuesta": True
            }
        ]
    },

    {
        "id": "B2",
        "nombre": "Grupo de 2 personas",
        "turnos": [
            {
                "input": "Hola, somos solo 2 personas para Golden Hour",
                "criterios": [
                    ("bravo_290",          False, r"bravo 290",                              "Recomienda Bravo 290 (1-5 pax)"),
                    ("no_firpol",          True,  r"firpol",                                 "No recomienda Firpol (sobrecapacidad)"),
                    ("precio",             False, r"\$|usd|cop|\d{3,}",                      "Presenta precio"),
                    ("no_reactiva",        True,  r"cu[aá]l.{0,30}golden.*\?",               "No re-pregunta la experiencia"),
                ],
                "guardar_respuesta": True
            }
        ]
    },

    {
        "id": "B3",
        "nombre": "Grupo de 15 personas",
        "turnos": [
            {
                "input": "Somos 15 personas para Islas del Rosario",
                "criterios": [
                    ("bravo_410",          False, r"bravo 410",                              "Recomienda Bravo 410 (13-19 pax)"),
                    ("no_firpol34",        True,  r"firpol 34",                              "No recomienda Firpol 34 (poca capacidad)"),
                    ("precio",             False, r"\$|usd|cop|\d{3,}",                      "Presenta precio"),
                ],
                "guardar_respuesta": True
            }
        ]
    },

    {
        "id": "C1",
        "nombre": "Upsell — cumpleaños / señal de lujo",
        "turnos": [
            {
                "input": "Somos 4, es el cumpleaños de mi esposa, queremos algo muy especial y exclusivo",
                "criterios": [
                    ("azimut_70",          False, r"azimut 70",                              "Ofrece Azimut 70 primero"),
                    ("no_azimut_55",       True,  r"azimut 55",                              "No baja directo al Azimut 55"),
                    ("justifica_exp",      False, r"exclusiv|especial|celebr|diferente|experiencia|lujo", "Justifica experiencia antes del precio"),
                    ("no_bravo",           True,  r"bravo 290",                              "No recomienda Bravo 290 con señal de lujo"),
                    ("no_menu_yates",      True,  r"azimut 70.{0,100}azimut 62|azimut 62.{0,100}azimut 70", "No presenta múltiples yates"),
                ],
                "guardar_respuesta": True
            }
        ]
    },

    {
        "id": "C2",
        "nombre": "Upsell — cliente pide algo más grande (cascada)",
        "turnos": [
            {
                "input": "Somos 10 para Islas del Rosario",
                "criterios": [
                    ("firpol_34_base",     False, r"firpol 34",                              "Recomienda Firpol 34 como base"),
                ],
                "guardar_respuesta": False
            },
            {
                "input": "¿Tienen algo más grande y más cómodo?",
                "criterios": [
                    ("sube_nivel",         False, r"bravo 380|bravo 410|tuna",               "Sube un nivel en la cascada"),
                    ("no_yate_directo",    True,  r"azimut",                                 "No salta directo a yate sin señal premium"),
                    ("no_salto_doble",     True,  r"todomar",                                "No salta dos niveles"),
                    ("una_embarcacion",    False, r"^(?:(?!bravo 380.{0,200}bravo 410).)*$", "Presenta una sola embarcación"),
                ],
                "guardar_respuesta": True
            }
        ]
    },

    {
        "id": "D1",
        "nombre": "Lead desde landing — datos completos",
        "turnos": [
            {
                "input": (
                    "Source: landing\n"
                    "Full name: Michael Torres\n"
                    "Phone: +13055559876\n"
                    "Email: michael@example.com\n"
                    "Plan: islas_del_rosario\n"
                    "Passengers: 6\n"
                    "Preferred date: 2026-04-10\n"
                    "Language: es"
                ),
                "criterios": [
                    ("registra_lead",      False, r"registr",                                "Ejecuta registrar_lead"),
                    ("recomendacion",      False, r"firpol 34",                              "Recomienda Firpol 34 (6 pax)"),
                    ("precio",             False, r"\$|usd|cop|\d{3,}",                      "Presenta precio"),
                    ("no_reactiva_exp",    True,  r"cu[aá]l.{0,30}(golden|islas).*\?",       "No re-pregunta experiencia"),
                    ("no_reactiva_pax",    True,  r"cu[aá]ntas personas",                    "No re-pregunta número de personas"),
                    ("no_reactiva_fecha",  True,  r"cu[aá]l.{0,20}fecha|cu[aá]ndo van",      "No re-pregunta la fecha"),
                ],
                "guardar_respuesta": True
            }
        ]
    },

    {
        "id": "E1",
        "nombre": "Objeción de precio — niveles de cierre en orden",
        "turnos": [
            {
                "input": "Somos 4 para Islas del Rosario",
                "criterios": [],
                "guardar_respuesta": False
            },
            {
                "input": "Está muy caro",
                "criterios": [
                    ("nivel_1_o_2",        False, r"asegur|env[ií]o.*link|hoy|link de pago", "Activa Nivel 1 o 2 de cierre"),
                    ("no_descuento_aun",   True,  r"10\s*%|10 por ciento|descuento",         "NO ofrece 10% en primera objeción"),
                ],
                "guardar_respuesta": False
            },
            {
                "input": "No, de verdad no puedo pagarlo, es demasiado para mí",
                "criterios": [
                    ("descuento_10",       False, r"10\s*%|10 por ciento",                   "Activa descuento 10% en segunda objeción"),
                    ("pago_inmediato",     False, r"hoy|ahora|inmediato|mismo",               "Condiciona a pago 100% inmediato"),
                    ("link_pago",          False, r"link|pago|reserv",                       "Ofrece link de pago"),
                ],
                "guardar_respuesta": True
            }
        ]
    },

    {
        "id": "F1",
        "nombre": "Fecha pasada — rechazo correcto",
        "turnos": [
            {
                "input": "Somos 6 para Islas del Rosario",
                "criterios": [],
                "guardar_respuesta": False
            },
            {
                "input": "Queremos ir el 15 de enero de 2024",
                "criterios": [
                    ("rechaza_fecha",      False, r"pasad|anterior|v[aá]lid|futura|pr[oó]xim|disponible", "Rechaza fecha pasada"),
                    ("no_confirma",        True,  r"perfecto|anotad|reservad|confirmad",     "No confirma fecha pasada"),
                    ("pide_fecha_nueva",   False, r"fecha|d[ií]a|\?",                        "Solicita fecha nueva"),
                ],
                "guardar_respuesta": True
            }
        ]
    },

    {
        "id": "F2",
        "nombre": "No usa la palabra 'lancha'",
        "turnos": [
            {
                "input": "¿Qué tipo de lancha me recomiendan para 8 personas?",
                "criterios": [
                    ("no_lancha",          True,  r"\blancha\b",                             "Nunca usa la palabra 'lancha'"),
                    ("usa_nombre_oficial", False, r"firpol 34|bravo|embarcaci",              "Usa nombre oficial de embarcación"),
                ],
                "guardar_respuesta": True
            }
        ]
    },

    {
        "id": "F3",
        "nombre": "Regla Firpol 42 — no se ofrece como opción inicial",
        "turnos": [
            {
                "input": "Somos 12 personas para Islas del Rosario",
                "criterios": [
                    ("bravo_380",          False, r"bravo 380",                              "Recomienda Bravo 380 (11-12 pax)"),
                    ("no_firpol42_inicial",True,  r"firpol 42",                              "No ofrece Firpol 42 como opción inicial"),
                ],
                "guardar_respuesta": True
            }
        ]
    },

    {
        "id": "G1",
        "nombre": "Stress multi-turno — aniversario con cambio de idioma",
        "turnos": [
            {
                "input": "Hola, somos 6 personas y queremos algo muy exclusivo para nuestro aniversario de bodas",
                "criterios": [
                    ("activa_upsell",      False, r"azimut|yate|exclusiv",                   "Detecta señal premium y activa upsell"),
                    ("no_bravo_290",       True,  r"bravo 290",                              "No recomienda bote estándar"),
                ],
                "guardar_respuesta": False
            },
            {
                "input": "That sounds amazing! Can you tell me more about what's included?",
                "criterios": [
                    ("cambia_ingles",      False, r"\b(the|and|for|include|our)\b",          "Cambia al inglés correctamente"),
                    ("no_espanol_mezcla",  True,  r"\b(hola|para|con|las|los)\b",            "No mezcla idiomas"),
                ],
                "guardar_respuesta": False
            },
            {
                "input": "Is there something even bigger?",
                "criterios": [
                    ("sube_cascada",       False, r"azimut 70|azimut 62|leopard",            "Sube en cascada premium"),
                    ("no_baja_nivel",      True,  r"azimut 55",                              "No baja de nivel sin objeción"),
                ],
                "guardar_respuesta": False
            },
            {
                "input": "Wow that's really expensive",
                "criterios": [
                    ("cierre_nivel1_2",    False, r"today|secure|link|book|asegur",          "Activa cierre Nivel 1 o 2"),
                    ("no_descuento",       True,  r"10%|10 percent|discount",                "No ofrece descuento en primera objeción"),
                ],
                "guardar_respuesta": False
            },
            {
                "input": "I really can't pay that, it's way too much for us",
                "criterios": [
                    ("descuento_final",    False, r"10%|10 percent|discount",                "Activa descuento 10% en segunda objeción"),
                    ("condicion_pago",     False, r"today|now|right now|immediately",        "Exige pago inmediato como condición"),
                ],
                "guardar_respuesta": True
            }
        ]
    }

]

def correr_escenario(system_prompt, escenario):
    historial = []
    resultados_escenario = []
    ultima_respuesta = ""

    for i, turno in enumerate(escenario["turnos"]):
        historial.append({"role": "user", "content": turno["input"]})
        respuesta = llamar(system_prompt, historial)
        historial.append({"role": "assistant", "content": respuesta})

        if turno.get("guardar_respuesta"):
            ultima_respuesta = respuesta

        for cid, negativo, patron, desc in turno["criterios"]:
            paso = check(respuesta, patron, negativo)
            resultados_escenario.append({
                "turno": i+1,
                "criterio": cid,
                "descripcion": desc,
                "pass": paso,
                "respuesta": respuesta if turno.get("guardar_respuesta") else ""
            })

    return resultados_escenario, ultima_respuesta

def main():
    print("\n🚤  BOATS4U — Stress Test Laura 5.1")
    print(f"    Modelo : {MODEL}")
    print(f"    Fecha  : {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}")

    try:
        system_prompt = cargar_prompt()
    except FileNotFoundError:
        print(f"\n❌  No se encontró {SYSTEM_FILE}. Asegúrate de tenerlo en la misma carpeta.")
        return

    lineas_output = []
    lineas_output.append("=" * 65)
    lineas_output.append("BOATS4U — RESULTADO STRESS TEST LAURA 5.1")
    lineas_output.append(f"Modelo: {MODEL}")
    lineas_output.append(f"Fecha : {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}")
    lineas_output.append("=" * 65)

    total_pass = 0
    total_fail = 0
    escenarios_pass = 0
    escenarios_fail = 0

    for esc in ESCENARIOS:
        print(f"\n⏳  [{esc['id']}] {esc['nombre']}...")
        try:
            resultados, ultima_resp = correr_escenario(system_prompt, esc)
        except Exception as e:
            print(f"   ❌  Error: {e}")
            lineas_output.append(f"\n[{esc['id']}] {esc['nombre']} — ERROR: {e}")
            continue

        esc_pass = all(r["pass"] for r in resultados)
        if esc_pass:
            escenarios_pass += 1
        else:
            escenarios_fail += 1

        status = "✅ PASS" if esc_pass else "❌ FAIL"
        print(f"   {status}")

        lineas_output.append(f"\n{'─' * 65}")
        lineas_output.append(f"[{esc['id']}] {esc['nombre']}  →  {status}")
        lineas_output.append(f"{'─' * 65}")

        for r in resultados:
            icon = "✅" if r["pass"] else "❌"
            lineas_output.append(f"  {icon}  [T{r['turno']}] {r['descripcion']}")
            if not r["pass"]:
                total_fail += 1
            else:
                total_pass += 1

        if ultima_resp:
            lineas_output.append(f"\n  Última respuesta de Laura:")
            lineas_output.append(f"  {ultima_resp[:500]}{'...' if len(ultima_resp)>500 else ''}")

    total_criterios = total_pass + total_fail
    pct = round(total_pass / total_criterios * 100) if total_criterios > 0 else 0

    lineas_output.append(f"\n{'=' * 65}")
    lineas_output.append(f"RESUMEN FINAL")
    lineas_output.append(f"{'=' * 65}")
    lineas_output.append(f"Escenarios : {escenarios_pass}/{escenarios_pass+escenarios_fail} PASS")
    lineas_output.append(f"Criterios  : {total_pass}/{total_criterios} PASS  ({pct}%)")

    veredicto = "🎉 LISTA PARA PRODUCCIÓN" if pct >= 90 else "⚠️  REQUIERE REVISIÓN" if pct >= 70 else "❌ FALLA CRÍTICA"
    lineas_output.append(f"Veredicto  : {veredicto}")
    lineas_output.append("=" * 65)

    output_text = "\n".join(lineas_output)
    with open(OUTPUT, "w", encoding="utf-8") as f:
        f.write(output_text)

    print(f"\n{output_text}")
    print(f"\n💾  Resultado guardado en: {OUTPUT}")

if __name__ == "__main__":
    main()
