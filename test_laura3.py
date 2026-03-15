"""
test_laura3.py — Nivel 3: Escenario Exhaustivo Multi-Turno
Laura 5.1 — Boats4U

Simula un cliente caótico que cambia de todo: plan, personas,
idioma, sube, baja, objeta y finalmente reserva.

Cómo correr:
    python test_laura3.py

Salida: resultado_test_laura3.txt
"""

import os
import re
import datetime
import anthropic

API_KEY = os.environ.get("ANTHROPIC_API_KEY", "REEMPLAZA_TU_KEY_AQUI")
MODEL   = "claude-sonnet-4-6"
OUTPUT  = "laura_test4.txt"

PRECIOS_DUMMY = """
---
## TABLA DE PRECIOS OFICIALES (USAR SIEMPRE ESTOS VALORES)

| Plan               | Embarcación  | Precio COP      | Precio USD |
|--------------------|-------------|-----------------|------------|
| Golden Hour        | Bravo 290   | $650.000 COP    | $160 USD   |
| Golden Hour        | Firpol 34   | $1.200.000 COP  | $290 USD   |
| Golden Hour        | Bravo 380   | $1.800.000 COP  | $440 USD   |
| Golden Hour        | Bravo 410   | $2.200.000 COP  | $540 USD   |
| Golden Hour        | Todomar 44  | $2.800.000 COP  | $680 USD   |
| Golden Hour        | Azimut 55   | $4.500.000 COP  | $1.100 USD |
| Golden Hour        | Azimut 58   | $5.200.000 COP  | $1.270 USD |
| Golden Hour        | Azimut 62   | $6.000.000 COP  | $1.460 USD |
| Golden Hour        | Azimut 70   | $7.500.000 COP  | $1.830 USD |
| Golden Hour        | Leopard 43  | $5.800.000 COP  | $1.415 USD |
| Golden Hour        | Leopard 51  | $7.000.000 COP  | $1.710 USD |
| Islas del Rosario  | Bravo 290   | $1.400.000 COP  | $340 USD   |
| Islas del Rosario  | Firpol 34   | $2.400.000 COP  | $585 USD   |
| Islas del Rosario  | Bravo 380   | $3.200.000 COP  | $780 USD   |
| Islas del Rosario  | Bravo 410   | $4.000.000 COP  | $975 USD   |
| Islas del Rosario  | Todomar 44  | $5.200.000 COP  | $1.270 USD |
| Islas del Rosario  | Azimut 55   | $8.500.000 COP  | $2.075 USD |
| Islas del Rosario  | Azimut 58   | $9.800.000 COP  | $2.390 USD |
| Islas del Rosario  | Azimut 62   | $11.500.000 COP | $2.805 USD |
| Islas del Rosario  | Azimut 70   | $14.000.000 COP | $3.415 USD |
| Islas del Rosario  | Leopard 43  | $10.500.000 COP | $2.560 USD |
| Islas del Rosario  | Leopard 51  | $13.000.000 COP | $3.170 USD |

Regla de moneda:
- Cliente en español → presentar precio en COP
- Cliente en inglés → presentar precio en USD
---
"""

def cargar_prompt():
    with open("laura_5.1.claudecode.md", encoding="utf-8") as f:
        content = f.read()
    content = content.replace("{{CURRENT_DATETIME}}", "2026-03-15 20:45")
    content += "\n\n" + PRECIOS_DUMMY
    return content

client = anthropic.Anthropic(api_key=API_KEY)

def llamar(system, messages):
    import time
    delays = [15, 30, 60, 120]
    for attempt, delay in enumerate(delays + [None]):
        try:
            r = client.messages.create(
                model=MODEL,
                max_tokens=1024,
                system=system,
                messages=messages
            )
            return r.content[0].text
        except anthropic.RateLimitError:
            if delay is None:
                raise
            print(f"   ⏸  Rate limit — reintentando en {delay}s (intento {attempt+1}/4)...")
            time.sleep(delay)

def check(texto, patron, negativo=False):
    encontrado = bool(re.search(patron, texto, re.IGNORECASE | re.DOTALL))
    return (not encontrado) if negativo else encontrado

ESCENARIO = {
    "id": "STRESS-01",
    "nombre": "Cliente caótico — cambia todo, objeta, cambia idioma y reserva",
    "descripcion": """
    Conversación de 12 turnos. El cliente cambia de plan, sube y baja pasajeros,
    pide lujo, objeta el precio dos veces, cambia a inglés, intenta una fecha
    pasada, y finalmente reserva.
    """,
    "turnos": [
        {
            "label": "T1 — Saludo simple",
            "input": "Hola",
            "criterios": [
                ("saludo_noche",     False, r"buenas noches",                               "Saludo nocturno correcto"),
                ("emoji",           False, r"[⚓🚤🌊🌅]",                                  "Emoji náutico presente"),
                ("ambas_exp",       False, r"golden hour.{0,200}islas|islas.{0,200}golden", "Presenta ambas experiencias"),
                ("pregunta_cierre", False, r"cu[aá]l.{0,50}\?",                             "Cierra con pregunta de elección"),
                ("no_precio_t1",    True,  r"\$|\d{3,}",                                    "No menciona precio en T1"),
                ("no_fecha_t1",     True,  r"fecha|cu[aá]ndo",                              "No pregunta fecha en T1"),
            ]
        },
        {
            "label": "T2 — Elige Golden Hour",
            "input": "Quiero el Golden Hour",
            "criterios": [
                ("pide_personas",   False, r"cu[aá]ntas|cu[aá]ntos|personas|son",           "Pregunta número de personas"),
                ("no_reactiva_exp", True,  r"cu[aá]l.{0,30}golden.*\?",                     "No re-pregunta la experiencia"),
                ("una_pregunta",    False, r"^[^?]*\?[^?]*$",                               "Solo una pregunta"),
            ]
        },
        {
            "label": "T3 — Da personas para Golden Hour",
            "input": "Somos 5 personas",
            "criterios": [
                ("bravo_290",       False, r"bravo 290",                                    "Recomienda Bravo 290 (1-5 pax)"),
                ("precio_golden",   False, r"650|160",                                      "Precio correcto Golden Hour Bravo 290"),
                ("pregunta_fecha",  False, r"fecha|cu[aá]ndo|d[ií]a",                       "Pregunta por fecha"),
                ("no_menu",         True,  r"bravo 290.{0,100}firpol|firpol.{0,100}bravo 290", "No presenta múltiples botes"),
            ]
        },
        {
            "label": "T4 — Cambia a Islas del Rosario",
            "input": "Espera, mejor cambiemos a Islas del Rosario",
            "criterios": [
                ("acepta_cambio",   False, r"islas|rosario",                                "Acepta el cambio de experiencia"),
                ("mantiene_bote",   False, r"bravo 290",                                    "Mantiene el bote (5 pax no cambia)"),
                ("precio_islas",    False, r"1.400|340",                                    "Precio correcto Islas Bravo 290"),
                ("no_reactiva_pax", True,  r"cu[aá]ntas personas",                          "No re-pregunta personas"),
            ]
        },
        {
            "label": "T5 — Sube a 10 personas",
            "input": "Ah no espera, en realidad somos 10",
            "criterios": [
                ("firpol_34",       False, r"firpol 34",                                    "Actualiza a Firpol 34 (6-10 pax)"),
                ("precio_firpol",   False, r"2.400|585",                                    "Precio correcto Islas Firpol 34"),
                ("no_bravo_290",    True,  r"bravo 290",                                    "Ya no recomienda Bravo 290"),
                ("no_reactiva_exp", True,  r"cu[aá]l.{0,30}islas.*\?",                      "No re-pregunta la experiencia"),
            ]
        },
        {
            "label": "T6 — Señal de lujo / aniversario",
            "input": "Es nuestro aniversario de bodas número 10, queremos algo muy especial y exclusivo",
            "criterios": [
                ("azimut_70",       False, r"azimut 70",                                    "Ofrece Azimut 70 primero"),
                ("justifica_exp",   False, r"exclusiv|especial|lujo|diferente|celebr",      "Justifica experiencia antes del precio"),
                ("no_precio_yate",  True,  r"14.000|3.415",                                 "No menciona precio antes de justificar"),
                ("no_menu_yates",   True,  r"azimut 70.{0,100}azimut 62",                   "No presenta múltiples yates"),
            ]
        },
        {
            "label": "T7 — Cambia a inglés y pide detalles",
            "input": "That sounds incredible! What exactly is included in the Azimut 70 experience?",
            "criterios": [
                ("responde_ingles",  False, r"\b(the|and|include|our|you|this)\b",           "Responde en inglés"),
                ("no_espanol",       True,  r"\b(hola|las|los|para|con|nuestro)\b",          "No mezcla español"),
                ("precio_usd",       False, r"\$3.415|\$3,415|3.415 usd|3,415",             "Precio en USD al hablar inglés"),
            ]
        },
        {
            "label": "T8 — Primera objeción de precio",
            "input": "Wow that's really expensive for us",
            "criterios": [
                ("cierre_n1_n2",    False, r"today|secure|link|book|asegur|hoy",            "Activa cierre Nivel 1 o 2"),
                ("no_descuento",    True,  r"10\s*%|10 percent|discount",                   "No ofrece descuento todavía"),
                ("no_abandona",     True,  r"no problem|understood|entiendo|otra opci",      "No abandona la venta"),
            ]
        },
        {
            "label": "T9 — Segunda objeción — activa descuento",
            "input": "I really can't afford that, it's too much",
            "criterios": [
                ("descuento_10",    False, r"10\s*%|10 percent",                            "Activa descuento 10%"),
                ("pago_inmediato",  False, r"today|now|right now|immediately",              "Exige pago inmediato"),
                ("link_pago",       False, r"link|payment|pay",                             "Ofrece link de pago"),
                ("una_vez",         False, r"10\s*%",                                       "Menciona descuento"),
            ]
        },
        {
            "label": "T10 — Intenta fecha pasada",
            "input": "Ok, let's do it. We want to go on March 5th 2024",
            "criterios": [
                ("rechaza_fecha",   False, r"past|already|2024|future|upcoming|valid",      "Rechaza fecha pasada en inglés"),
                ("pide_fecha_nueva",False, r"\?",                                           "Pide fecha nueva"),
                ("no_confirma",     True,  r"perfect|confirm|noted|great",                  "No confirma fecha pasada"),
            ]
        },
        {
            "label": "T11 — Da fecha válida",
            "input": "Ok, April 20th 2026",
            "criterios": [
                ("acepta_fecha",    False, r"april 20|april|2026",                          "Acepta la fecha"),
                ("avanza_cierre",   False, r"name|nombre|email|correo|confirm|reserv",      "Avanza hacia confirmación"),
                ("no_reactiva",     True,  r"how many|cu[aá]ntos|experience|experiencia",   "No re-pregunta datos ya dados"),
            ]
        },
        {
            "label": "T12 — Da nombre y correo para confirmar",
            "input": "My name is Carlos Mendez, email carlos@gmail.com",
            "criterios": [
                ("resumen",         False, r"azimut 70|april|april 20|2026",                "Incluye resumen de reserva"),
                ("link_pago",       False, r"link|payment|pay|pago",                        "Envía link de pago"),
                ("politica_pago",   False, r"50%|50 percent|half",                          "Menciona política de pago 50/50"),
                ("no_inventa",      True,  r"confirmed|reserv.*done|all set",               "No confirma sin pago recibido"),
            ]
        },
    ]
}

def correr():
    print(f"\n{'='*65}")
    print(f"🚤  STRESS TEST EXHAUSTIVO — {ESCENARIO['nombre']}")
    print(ESCENARIO['descripcion'])
    print('='*65)

    try:
        system_prompt = cargar_prompt()
    except FileNotFoundError:
        print("❌  No se encontró LAURA_5_1.md")
        return

    historial = []
    resultados = []
    lineas = []

    lineas.append("=" * 65)
    lineas.append("BOATS4U — STRESS TEST EXHAUSTIVO LAURA 5.1")
    lineas.append(f"Escenario : {ESCENARIO['nombre']}")
    lineas.append(f"Modelo    : {MODEL}")
    lineas.append(f"Fecha     : {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}")
    lineas.append("=" * 65)

    total_pass = 0
    total_fail = 0

    for turno in ESCENARIO["turnos"]:
        print(f"\n⏳  {turno['label']}...")

        historial.append({"role": "user", "content": turno["input"]})
        respuesta = llamar(system_prompt, historial)
        historial.append({"role": "assistant", "content": respuesta})

        criterios_eval = []
        for cid, negativo, patron, desc in turno["criterios"]:
            paso = check(respuesta, patron, negativo)
            criterios_eval.append((cid, paso, desc))
            if paso:
                total_pass += 1
            else:
                total_fail += 1

        turno_pass = all(p for _, p, _ in criterios_eval)
        status = "✅ PASS" if turno_pass else "❌ FAIL"
        print(f"   {status}")

        lineas.append(f"\n{'─'*65}")
        lineas.append(f"{turno['label']}  →  {status}")
        lineas.append(f"Cliente : {turno['input']}")
        lineas.append(f"Laura   : {respuesta[:400]}{'...' if len(respuesta)>400 else ''}")
        lineas.append("")
        for cid, paso, desc in criterios_eval:
            icon = "✅" if paso else "❌"
            lineas.append(f"  {icon}  {desc}")

        resultados.append(turno_pass)

    turnos_pass = sum(resultados)
    turnos_total = len(resultados)
    total_criterios = total_pass + total_fail
    pct = round(total_pass / total_criterios * 100) if total_criterios > 0 else 0

    if pct >= 90:
        veredicto = "🎉 LISTA PARA PRODUCCIÓN"
    elif pct >= 75:
        veredicto = "⚠️  REQUIERE AJUSTES MENORES"
    else:
        veredicto = "❌ FALLA CRÍTICA — REVISAR PROMPT"

    lineas.append(f"\n{'='*65}")
    lineas.append("RESUMEN FINAL")
    lineas.append(f"{'='*65}")
    lineas.append(f"Turnos    : {turnos_pass}/{turnos_total} PASS")
    lineas.append(f"Criterios : {total_pass}/{total_criterios} PASS  ({pct}%)")
    lineas.append(f"Veredicto : {veredicto}")
    lineas.append("=" * 65)

    output = "\n".join(lineas)
    with open(OUTPUT, "w", encoding="utf-8") as f:
        f.write(output)

    print(f"\n{output}")
    print(f"\n💾  Guardado en: {OUTPUT}")

if __name__ == "__main__":
    correr()
