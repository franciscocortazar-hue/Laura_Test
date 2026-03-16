"""
test_laura_lab.py — Prueba de laboratorio final
Laura 5.5 — Boats4U

Cubre los puntos criticos de la version 5.5 antes del go-live en WhatsApp.

Correr:
    python test_laura_lab.py

Salida: resultado_lab_laura55.txt
"""

import os
import re
import datetime
import anthropic

API_KEY     = os.environ.get("ANTHROPIC_API_KEY", "REEMPLAZA_TU_KEY")
MODEL       = "claude-sonnet-4-6"
OUTPUT      = "resultado_lab_laura55.txt"
SYSTEM_FILE = "LAURA_5_5.md"

PRECIOS_DUMMY = """
---
TABLA DE PRECIOS OFICIALES

Plan               | Embarcacion   | COP             | USD
Golden Hour        | Bravo 290     | 650000          | 160
Golden Hour        | Firpol 34     | 1200000         | 290
Golden Hour        | Bravo 380     | 1800000         | 440
Golden Hour        | Bravo 410     | 2200000         | 540
Golden Hour        | Todomar 44    | 2800000         | 680
Golden Hour        | Azimut 55     | 4500000         | 1100
Golden Hour        | Azimut 58     | 5200000         | 1270
Golden Hour        | Azimut 62     | 6000000         | 1460
Golden Hour        | Azimut 70     | 7500000         | 1830
Golden Hour        | Leopard 43    | 5800000         | 1415
Golden Hour        | Leopard 51    | 7000000         | 1710
Islas del Rosario  | Bravo 290     | 1400000         | 340
Islas del Rosario  | Firpol 34     | 2400000         | 585
Islas del Rosario  | Bravo 380     | 3200000         | 780
Islas del Rosario  | Bravo 410     | 4000000         | 975
Islas del Rosario  | Todomar 44    | 5200000         | 1270
Islas del Rosario  | Azimut 55     | 8500000         | 2075
Islas del Rosario  | Azimut 58     | 9800000         | 2390
Islas del Rosario  | Azimut 62     | 11500000        | 2805
Islas del Rosario  | Azimut 70     | 14000000        | 3415
Islas del Rosario  | Leopard 43    | 10500000        | 2560
Islas del Rosario  | Leopard 51    | 13000000        | 3170

Regla de moneda: cliente en espanol presenta COP. Cliente en ingles presenta USD.
---
"""

def cargar_prompt():
    with open(SYSTEM_FILE, encoding="utf-8") as f:
        content = f.read()
    content = content.replace("{{CURRENT_DATETIME}}", "2026-03-16 20:30")
    return content + "\n\n" + PRECIOS_DUMMY

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

    # ── BLOQUE 1: FLUJO BASE ─────────────────────────────────────────────────

    {
        "id": "L01",
        "nombre": "Flujo completo de punta a punta — espanol",
        "desc": "Cliente elige Islas, da personas, recibe precio, da fecha, nombre, correo. Laura cierra con link.",
        "turnos": [
            {"input": "Hola",
             "criterios": [
                ("saludo",      False, r"buenas noches",                        "Saludo nocturno"),
                ("dos_exp",     False, r"golden.{0,100}islas|islas.{0,100}golden", "Presenta ambas experiencias"),
                ("pregunta",    False, r"cuál te llama|que te llama",            "Pregunta de eleccion"),
             ]},
            {"input": "Islas del Rosario",
             "criterios": [
                ("pide_pax",    False, r"cuantas|personas|son",                  "Pide numero de personas"),
                ("no_reactiva", True,  r"cuál.*golden|cuál.*islas",              "No re-pregunta experiencia"),
             ]},
            {"input": "Somos 6",
             "criterios": [
                ("firpol",      False, r"firpol 34",                             "Recomienda Firpol 34"),
                ("precio",      False, r"2.400|2400|585",                        "Presenta precio correcto"),
                ("pide_fecha",  False, r"fecha|cuando|dia",                      "Pide fecha"),
             ]},
            {"input": "El 5 de abril",
             "criterios": [
                ("acepta",      False, r"abril|5 de abril|april",                "Acepta la fecha"),
                ("avanza",      False, r"nombre|correo|reserv|confirm|pago",     "Avanza hacia confirmacion"),
             ]},
            {"input": "Carlos Ruiz, carlos@gmail.com",
             "criterios": [
                ("resumen",     False, r"islas|rosario",                         "Incluye experiencia en resumen"),
                ("link",        False, r"link|pago",                             "Envia link de pago"),
                ("politica",    False, r"50",                                    "Menciona politica 50/50"),
                ("no_confirm",  True,  r"confirmad|reservad",                    "No dice confirmada antes del pago"),
             ]},
        ]
    },

    # ── BLOQUE 2: CANTIDADES EN LENGUAJE NATURAL ─────────────────────────────

    {
        "id": "L02",
        "nombre": "Cantidad en letras — somos trece",
        "desc": "Cliente dice somos trece. Laura debe interpretar 13 y recomendar Bravo 410.",
        "turnos": [
            {"input": "Somos trece para Islas del Rosario",
             "criterios": [
                ("bravo_410",   False, r"bravo 410",                             "Recomienda Bravo 410 (13 pax)"),
                ("precio",      False, r"4.000|4000|975",                        "Precio correcto"),
                ("no_firpol",   True,  r"firpol 34",                             "No recomienda Firpol 34"),
             ]},
        ]
    },

    {
        "id": "L03",
        "nombre": "Cantidad aditiva — doce mas uno",
        "desc": "Cliente dice somos doce mas uno. Laura suma y recomienda Bravo 410.",
        "turnos": [
            {"input": "Somos doce mas uno para Golden Hour",
             "criterios": [
                ("bravo_410",   False, r"bravo 410",                             "Recomienda Bravo 410 (13 pax)"),
                ("precio",      False, r"2.200|2200|540",                        "Precio correcto Golden Hour"),
             ]},
        ]
    },

    {
        "id": "L04",
        "nombre": "Singular implicito — voy solo",
        "desc": "Cliente dice voy solo. Laura interpreta 1 y recomienda Bravo 290 sin dudar.",
        "turnos": [
            {"input": "Voy solo para Golden Hour",
             "criterios": [
                ("bravo_290",   False, r"bravo 290",                             "Recomienda Bravo 290"),
                ("precio",      False, r"650|160",                               "Precio correcto"),
                ("no_pregunta", True,  r"cuantas|personas|grupo",                "No pregunta por mas personas"),
             ]},
        ]
    },

    {
        "id": "L05",
        "nombre": "Pareja",
        "desc": "Cliente dice somos una pareja. Laura interpreta 2 y recomienda Bravo 290.",
        "turnos": [
            {"input": "Somos una pareja para Islas del Rosario",
             "criterios": [
                ("bravo_290",   False, r"bravo 290",                             "Recomienda Bravo 290 (2 pax)"),
                ("precio",      False, r"1.400|1400|340",                        "Precio correcto"),
             ]},
        ]
    },

    # ── BLOQUE 3: CAMBIOS EN MID-CONVERSACION ────────────────────────────────

    {
        "id": "L06",
        "nombre": "Cambia de experiencia — Golden a Islas",
        "desc": "Cliente empieza con Golden Hour, luego cambia a Islas. Laura actualiza precio sin re-preguntar personas.",
        "turnos": [
            {"input": "Somos 4 para Golden Hour",          "criterios": []},
            {"input": "Mejor Islas del Rosario",
             "criterios": [
                ("acepta",      False, r"islas|rosario",                         "Acepta el cambio"),
                ("precio_nuevo",False, r"1.400|1400|340",                        "Precio correcto Islas Bravo 290"),
                ("no_repregunta",True, r"cuantas personas",                      "No re-pregunta personas"),
             ]},
        ]
    },

    {
        "id": "L07",
        "nombre": "Sube de 5 a 12 personas",
        "desc": "Cliente empieza con 5, luego corrige a 12. Laura actualiza a Bravo 380.",
        "turnos": [
            {"input": "Somos 5 para Islas del Rosario",    "criterios": []},
            {"input": "En realidad somos doce",
             "criterios": [
                ("bravo_380",   False, r"bravo 380",                             "Actualiza a Bravo 380 (12 pax)"),
                ("precio",      False, r"3.200|3200|780",                        "Precio correcto"),
                ("no_bravo_290",True,  r"bravo 290",                             "No menciona Bravo 290"),
             ]},
        ]
    },

    # ── BLOQUE 4: UPSELL SOLO POR SOLICITUD ──────────────────────────────────

    {
        "id": "L08",
        "nombre": "Celebracion NO activa yate — flujo base",
        "desc": "Cliente menciona aniversario. Laura recomienda bote base segun pax, no yate.",
        "turnos": [
            {"input": "Somos 2 para Islas del Rosario, es nuestro aniversario",
             "criterios": [
                ("bravo_290",   False, r"bravo 290",                             "Recomienda Bravo 290 (flujo base)"),
                ("no_yate",     True,  r"azimut|leopard",                        "No ofrece yate sin solicitud"),
             ]},
        ]
    },

    {
        "id": "L09",
        "nombre": "Upsell activado por solicitud explicita",
        "desc": "Cliente pide algo mas lujoso. Laura activa cascada premium con Azimut 70.",
        "turnos": [
            {"input": "Somos 4 para Islas del Rosario",    "criterios": []},
            {"input": "Quiero algo mas lujoso y exclusivo",
             "criterios": [
                ("azimut_70",   False, r"azimut 70",                             "Ofrece Azimut 70 primero"),
                ("no_azimut_55",True,  r"azimut 55",                             "No empieza por Azimut 55"),
                ("justifica",   False, r"exclusiv|lujo|privacidad|experiencia",  "Justifica antes del precio"),
             ]},
        ]
    },

    {
        "id": "L10",
        "nombre": "Descenso en cascada — un nivel a la vez",
        "desc": "Cliente en Azimut 70 pide algo mas pequeno. Laura baja a Azimut 62, no a Azimut 55.",
        "turnos": [
            {"input": "Somos 2, quiero un yate para Islas del Rosario",          "criterios": []},
            {"input": "Algo mas pequeno por favor",
             "criterios": [
                ("azimut_62",   False, r"azimut 62",                             "Baja a Azimut 62"),
                ("no_azimut_55",True,  r"azimut 55",                             "No salta al Azimut 55"),
                ("no_leopard",  True,  r"leopard",                               "No salta a catamaran"),
             ]},
        ]
    },

    # ── BLOQUE 5: FECHAS ─────────────────────────────────────────────────────

    {
        "id": "L11",
        "nombre": "Fecha pasada — rechaza",
        "desc": "Cliente da fecha de 2024. Laura rechaza y pide fecha nueva.",
        "turnos": [
            {"input": "Somos 4 para Golden Hour",          "criterios": []},
            {"input": "Queremos el 10 de enero de 2024",
             "criterios": [
                ("rechaza",     False, r"pas[ao]|anterior|2024|ya pas",          "Rechaza fecha pasada"),
                ("pide_nueva",  False, r"\?",                                    "Pide fecha nueva"),
                ("no_acepta",   True,  r"perfecto|anotado|reservado",            "No acepta la fecha"),
             ]},
        ]
    },

    {
        "id": "L12",
        "nombre": "Fecha ambigua — no infiere",
        "desc": "Cliente dice el proximo sabado. Laura pide el dia exacto sin calcular.",
        "turnos": [
            {"input": "Somos 6 para Islas del Rosario",    "criterios": []},
            {"input": "Queremos ir el proximo sabado",
             "criterios": [
                ("pide_exacta", False, r"dia|mes|exacto|\?",                     "Pide dia y mes exactos"),
                ("no_infiere",  True,  r"21 de marzo|march 21|sabado \d",        "No calcula ni infiere la fecha"),
                ("no_acepta",   True,  r"^perfecto\.|^entendido\.",              "No abre con afirmacion"),
             ]},
        ]
    },

    # ── BLOQUE 6: ESTRATEGIA DE CIERRE ───────────────────────────────────────

    {
        "id": "L13",
        "nombre": "Primera objecion — Nivel 1 o 2",
        "desc": "Cliente dice esta muy caro. Laura activa cierre sin descuento y sin bajar bote.",
        "turnos": [
            {"input": "Somos 4 para Islas del Rosario",    "criterios": []},
            {"input": "Esta muy caro",
             "criterios": [
                ("cierre",      False, r"asegur|link|hoy|envio",                 "Activa Nivel 1 o 2 de cierre"),
                ("no_descuento",True,  r"10\s*%|descuento",                      "No da descuento todavia"),
                ("no_baja_bote",True,  r"bravo 290|algo mas pequeño",            "No baja de embarcacion"),
             ]},
        ]
    },

    {
        "id": "L14",
        "nombre": "Segunda objecion — activa Nivel 3",
        "desc": "Cliente objeta por segunda vez. Laura activa descuento 10% con pago inmediato.",
        "turnos": [
            {"input": "Somos 4 para Islas del Rosario",    "criterios": []},
            {"input": "Esta muy caro",                     "criterios": []},
            {"input": "No de verdad no puedo pagarlo",
             "criterios": [
                ("descuento",   False, r"10\s*%|10 por ciento",                  "Activa descuento 10%"),
                ("pago_hoy",    False, r"hoy|ahora|inmediato",                   "Exige pago inmediato"),
                ("link",        False, r"link|pago",                             "Ofrece link"),
             ]},
        ]
    },

    {
        "id": "L15",
        "nombre": "Cierre en ingles — segunda objecion activa descuento",
        "desc": "Flujo completo en ingles. Segunda objecion activa 10% off.",
        "turnos": [
            {"input": "We are 4 for the Rosario Islands",  "criterios": []},
            {"input": "That's too expensive",              "criterios": []},
            {"input": "I really can't afford it",
             "criterios": [
                ("descuento_en",False, r"10\s*%|10 percent|10% off",             "Activa descuento en ingles"),
                ("pago_en",     False, r"today|right now|immediately|full payment", "Exige pago inmediato en ingles"),
                ("no_budget",   True,  r"budget|presupuesto|what.*budget",       "No pregunta por presupuesto"),
             ]},
        ]
    },

    # ── BLOQUE 7: REGLAS OPERATIVAS ──────────────────────────────────────────

    {
        "id": "L16",
        "nombre": "Precio directo cuando bote y experiencia estan dados",
        "desc": "Cliente pregunta precio de Bravo 410 para Islas. Laura da precio sin pedir pax.",
        "turnos": [
            {"input": "Cuanto cuesta el Bravo 410 para Islas del Rosario",
             "criterios": [
                ("precio",      False, r"4.000|4000|975",                        "Da precio correcto directamente"),
                ("no_pide_pax", True,  r"cuantas personas|cuantos son",          "No pide numero de pasajeros"),
             ]},
        ]
    },

    {
        "id": "L17",
        "nombre": "No usa la palabra lancha",
        "desc": "Cliente pregunta por una lancha. Laura nunca usa esa palabra.",
        "turnos": [
            {"input": "Que lancha tienen para 8 personas",
             "criterios": [
                ("no_lancha",   True,  r"\blancha\b",                            "No usa la palabra lancha"),
                ("firpol",      False, r"firpol 34",                             "Recomienda Firpol 34 por nombre oficial"),
             ]},
        ]
    },

    {
        "id": "L18",
        "nombre": "Firpol 42 no se ofrece inicial",
        "desc": "12 personas. Laura recomienda Bravo 380, no Firpol 42.",
        "turnos": [
            {"input": "Somos 12 para Golden Hour",
             "criterios": [
                ("bravo_380",   False, r"bravo 380",                             "Recomienda Bravo 380 (11-12 pax)"),
                ("no_firpol42", True,  r"firpol 42",                             "No ofrece Firpol 42"),
             ]},
        ]
    },

    {
        "id": "L19",
        "nombre": "Lead desde landing — datos completos",
        "desc": "Mensaje con Source: landing. Laura ejecuta registrar_lead y va directo a recomendacion.",
        "turnos": [
            {"input": (
                "Source: landing\n"
                "Full name: Sarah Johnson\n"
                "Phone: +13055559876\n"
                "Email: sarah@example.com\n"
                "Plan: golden_hour\n"
                "Passengers: 3\n"
                "Preferred date: 2026-05-01\n"
                "Language: en"
            ),
             "criterios": [
                ("registra",    False, r"registrar_lead|registrado|registr",     "Ejecuta registrar_lead"),
                ("bravo_290",   False, r"bravo 290",                             "Recomienda Bravo 290 (3 pax)"),
                ("precio_usd",  False, r"\$160|160 usd",                         "Precio en USD"),
                ("no_repregunta",True, r"which experience|how many|cuantas",     "No re-pregunta datos ya dados"),
             ]},
        ]
    },

    {
        "id": "L20",
        "nombre": "Rechazo explicito — cierre elegante sin frases prohibidas",
        "desc": "Cliente dice que no quiere. Laura cierra con dignidad sin usar frases de call center.",
        "turnos": [
            {"input": "Somos 4 para Islas del Rosario",    "criterios": []},
            {"input": "No gracias, no me interesa",
             "criterios": [
                ("no_insiste",  True,  r"asegur|link|descuento|10\s*%",          "No insiste ante rechazo"),
                ("no_prohib",   True,  r"sin problema|no worries|entendido, sin","No usa frases prohibidas"),
                ("cierra_bien", False, r"cartagena|mar|aqui estamos|here",       "Cierra con elegancia"),
             ]},
        ]
    },

]


def correr_escenario(system_prompt, escenario):
    historial = []
    resultados = []
    ultima_resp = ""

    for turno in escenario["turnos"]:
        historial.append({"role": "user", "content": turno["input"]})
        respuesta = llamar(system_prompt, historial)
        historial.append({"role": "assistant", "content": respuesta})
        ultima_resp = respuesta

        for cid, neg, patron, desc in turno["criterios"]:
            paso = check(respuesta, patron, neg)
            resultados.append({"id": cid, "desc": desc, "pass": paso, "resp": respuesta})

    return resultados, ultima_resp


def main():
    print(f"\n{'='*60}")
    print(f"BOATS4U — Lab Test Final Laura 5.5")
    print(f"Modelo : {MODEL}")
    print(f"Fecha  : {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"{'='*60}")

    try:
        system_prompt = cargar_prompt()
    except FileNotFoundError:
        print(f"No se encontro {SYSTEM_FILE}")
        return

    lineas = []
    lineas.append("=" * 60)
    lineas.append("BOATS4U — LAB TEST FINAL LAURA 5.5")
    lineas.append(f"Modelo : {MODEL}")
    lineas.append(f"Fecha  : {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}")
    lineas.append("=" * 60)

    total_pass = 0
    total_fail = 0
    esc_pass = 0
    esc_fail = 0

    for esc in ESCENARIOS:
        print(f"\n  [{esc['id']}] {esc['nombre']}...")

        try:
            resultados, ultima_resp = correr_escenario(system_prompt, esc)
        except Exception as e:
            print(f"  ERROR: {e}")
            lineas.append(f"\n[{esc['id']}] ERROR: {e}")
            esc_fail += 1
            continue

        esc_ok = all(r["pass"] for r in resultados)
        esc_pass += 1 if esc_ok else 0
        esc_fail += 0 if esc_ok else 1
        status = "PASS" if esc_ok else "FAIL"
        print(f"  {status}")

        lineas.append(f"\n{'─'*60}")
        lineas.append(f"[{esc['id']}] {esc['nombre']}  {status}")
        lineas.append(f"Desc: {esc['desc']}")
        lineas.append(f"Laura: {ultima_resp[:350]}{'...' if len(ultima_resp)>350 else ''}")
        lineas.append("")

        for r in resultados:
            icon = "OK  " if r["pass"] else "FAIL"
            lineas.append(f"  {icon}  {r['desc']}")
            total_pass += 1 if r["pass"] else 0
            total_fail += 0 if r["pass"] else 1

    total = total_pass + total_fail
    pct = round(total_pass / total * 100) if total > 0 else 0

    if pct >= 95:
        veredicto = "LISTA PARA PRODUCCION"
    elif pct >= 85:
        veredicto = "REQUIERE AJUSTES MENORES"
    else:
        veredicto = "REVISAR PROMPT"

    lineas.append(f"\n{'='*60}")
    lineas.append("RESUMEN")
    lineas.append(f"{'='*60}")
    lineas.append(f"Escenarios : {esc_pass}/{esc_pass+esc_fail} PASS")
    lineas.append(f"Criterios  : {total_pass}/{total} PASS  ({pct}%)")
    lineas.append(f"Veredicto  : {veredicto}")
    lineas.append("=" * 60)

    output = "\n".join(lineas)
    with open(OUTPUT, "w", encoding="utf-8") as f:
        f.write(output)

    print(f"\n{output}")
    print(f"\nGuardado en: {OUTPUT}")


if __name__ == "__main__":
    main()
