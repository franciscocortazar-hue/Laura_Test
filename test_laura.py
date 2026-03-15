"""
test_laura.py — Suite de pruebas para Laura 5.1 (Boats4U Cartagena)
Modelo: claude-sonnet-4-6
5 escenarios de conversación contra la API de Anthropic
"""

import os
import anthropic
from pathlib import Path

# ── Configuración ──────────────────────────────────────────────────────────────
MODEL = "claude-sonnet-4-6"
SYSTEM_PROMPT_FILE = Path(__file__).parent / "LAURA_5_1.md"
MAX_TOKENS = 1024

# ── Cargar system prompt ────────────────────────────────────────────────────────
def load_system_prompt() -> str:
    with open(SYSTEM_PROMPT_FILE, "r", encoding="utf-8") as f:
        return f.read()

# ── Llamada a la API ────────────────────────────────────────────────────────────
def chat(client: anthropic.Anthropic, system: str, messages: list[dict]) -> str:
    response = client.messages.create(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        system=system,
        messages=messages,
    )
    return response.content[0].text

# ── Validaciones ────────────────────────────────────────────────────────────────
def check_no_forbidden_phrases(text: str) -> list[str]:
    """Detecta frases que Laura nunca debe usar (Sección 4.1)."""
    forbidden = [
        "procedemos a",
        "le informo que",
        "¿en qué más le puedo ayudar?",
        "claro que sí, con gusto",
        "lancha",
    ]
    return [p for p in forbidden if p.lower() in text.lower()]

def check_single_question(text: str) -> bool:
    """Verifica que no haya más de una pregunta por mensaje (Sección 3)."""
    question_marks = text.count("?")
    return question_marks <= 1

def check_max_lines(text: str, max_lines: int = 8) -> bool:
    """Verifica que el mensaje no exceda el límite de líneas (Sección 3)."""
    non_empty = [l for l in text.split("\n") if l.strip()]
    return len(non_empty) <= max_lines

def check_role_maintained(text: str) -> bool:
    """Verifica que Laura no rompa su rol (Sección 0)."""
    role_breaks = ["soy un asistente", "soy claude", "soy una ia", "como modelo de lenguaje"]
    return not any(rb in text.lower() for rb in role_breaks)

# ── Imprimir resultado de un escenario ─────────────────────────────────────────
def print_result(scenario_num: int, name: str, messages: list[dict],
                 response: str, checks: dict):
    separator = "─" * 70
    print(f"\n{'═' * 70}")
    print(f"  ESCENARIO {scenario_num}: {name}")
    print(f"{'═' * 70}")
    print(f"\n[CONVERSACIÓN]")
    for msg in messages:
        role_label = "👤 Cliente" if msg["role"] == "user" else "🤖 Laura"
        print(f"\n{role_label}:\n  {msg['content']}")
    print(f"\n🤖 Laura (respuesta evaluada):\n  {response}")
    print(f"\n{separator}")
    print(f"[VALIDACIONES]")
    all_passed = True
    for check_name, (passed, detail) in checks.items():
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"  {status}  {check_name}")
        if detail:
            print(f"         → {detail}")
        if not passed:
            all_passed = False
    print(f"\n  Resultado final: {'✅ APROBADO' if all_passed else '❌ CON OBSERVACIONES'}")
    return all_passed

# ── Escenarios de prueba ────────────────────────────────────────────────────────

def scenario_1_activation(client, system):
    """
    Escenario 1 — Activación conversacional estándar
    Espera: saludo con ambas experiencias + pregunta de cierre (Sección 9)
    """
    messages = [{"role": "user", "content": "Hola, buenos días"}]
    response = chat(client, system, messages)

    golden_hour_mentioned = "golden hour" in response.lower()
    islas_mentioned = "islas del rosario" in response.lower() or "rosario" in response.lower()
    closing_question = "¿cuál" in response.lower() or "cual" in response.lower()
    forbidden = check_no_forbidden_phrases(response)
    role_ok = check_role_maintained(response)
    lines_ok = check_max_lines(response)

    checks = {
        "Menciona Golden Hour": (golden_hour_mentioned, None),
        "Menciona Islas del Rosario": (islas_mentioned, None),
        "Incluye pregunta de cierre": (closing_question, None),
        "Sin frases prohibidas": (len(forbidden) == 0, f"Encontradas: {forbidden}" if forbidden else None),
        "Mantiene rol de Laura": (role_ok, None),
        "Límite de líneas": (lines_ok, None),
    }
    return print_result(1, "Activación conversacional — saludo inicial", messages, response, checks)


def scenario_2_experience_selection(client, system):
    """
    Escenario 2 — Cliente elige experiencia, Laura pide número de personas
    Espera: no volver a preguntar la experiencia; preguntar cuántas personas (Sección 8 + 10.1)
    """
    messages = [
        {"role": "user", "content": "Hola, quiero hacer el Golden Hour"},
    ]
    response = chat(client, system, messages)

    asks_pax = any(w in response.lower() for w in ["cuántas personas", "cuantas personas", "personas", "pasajeros", "¿cuántos", "cuantos"])
    no_repeat_experience = response.lower().count("golden hour") <= 1
    single_q = check_single_question(response)
    forbidden = check_no_forbidden_phrases(response)
    role_ok = check_role_maintained(response)

    checks = {
        "Pregunta número de personas": (asks_pax, None),
        "No repite elección de experiencia en exceso": (no_repeat_experience, None),
        "Una sola pregunta": (single_q, f"{response.count('?')} signos de pregunta" if not single_q else None),
        "Sin frases prohibidas": (len(forbidden) == 0, f"Encontradas: {forbidden}" if forbidden else None),
        "Mantiene rol de Laura": (role_ok, None),
    }
    return print_result(2, "Selección de experiencia — Golden Hour", messages, response, checks)


def scenario_3_boat_recommendation(client, system):
    """
    Escenario 3 — Cliente da grupo de 3 personas para Golden Hour
    Espera: recomendar Bravo 290 (tabla Sección 10.1: 1-5 pax)
    """
    messages = [
        {"role": "user", "content": "Quiero el Golden Hour"},
        {"role": "assistant", "content": "¡Qué buena elección! El Golden Hour es uno de esos momentos que Cartagena regala — la bahía al atardecer, el cielo encendiéndose, tú en el agua. ¿Cuántas personas van a ser?"},
        {"role": "user", "content": "Somos 3 personas"},
    ]
    response = chat(client, system, messages)

    recommends_bravo_290 = "bravo 290" in response.lower()
    no_menu = response.lower().count("bravo") <= 2
    forbidden = check_no_forbidden_phrases(response)
    role_ok = check_role_maintained(response)
    lines_ok = check_max_lines(response)

    checks = {
        "Recomienda Bravo 290 (1-5 pax)": (recommends_bravo_290, "No se encontró 'Bravo 290'" if not recommends_bravo_290 else None),
        "No presenta múltiples opciones como menú": (no_menu, None),
        "Sin frases prohibidas": (len(forbidden) == 0, f"Encontradas: {forbidden}" if forbidden else None),
        "Mantiene rol de Laura": (role_ok, None),
        "Límite de líneas": (lines_ok, None),
    }
    return print_result(3, "Recomendación de embarcación — 3 personas Golden Hour", messages, response, checks)


def scenario_4_upsell_luxury(client, system):
    """
    Escenario 4 — Cliente pide algo exclusivo/lujo (trigger upsell premium)
    Espera: Laura activa cascada premium, ofrece Azimut 70 primero (Sección 10.2)
    """
    messages = [
        {"role": "user", "content": "Quiero algo exclusivo y de lujo para mi aniversario, somos 2 personas"},
    ]
    response = chat(client, system, messages)

    premium_triggered = any(w in response.lower() for w in ["azimut", "yate", "catamarán", "catamaran", "leopard"])
    azimut_70_first = "azimut 70" in response.lower()
    no_multiple_options = response.lower().count("azimut") <= 2
    forbidden = check_no_forbidden_phrases(response)
    role_ok = check_role_maintained(response)

    checks = {
        "Activa cascada premium (yate/catamarán)": (premium_triggered, None),
        "Ofrece Azimut 70 como primera opción premium": (azimut_70_first, "Se espera que ofrezca Azimut 70 primero" if not azimut_70_first else None),
        "No presenta múltiples yates simultáneamente": (no_multiple_options, None),
        "Sin frases prohibidas": (len(forbidden) == 0, f"Encontradas: {forbidden}" if forbidden else None),
        "Mantiene rol de Laura": (role_ok, None),
    }
    return print_result(4, "Upsell premium — aniversario de lujo", messages, response, checks)


def scenario_5_past_date_rejection(client, system):
    """
    Escenario 5 — Cliente propone una fecha pasada
    Espera: Laura rechaza la fecha y pide una válida (Sección 12)
    """
    messages = [
        {"role": "user", "content": "Quiero reservar el Golden Hour para el 10 de enero de 2024, somos 4 personas"},
    ]
    response = chat(client, system, messages)

    rejects_past_date = any(w in response.lower() for w in [
        "pasada", "ya pasó", "ya paso", "no puedo aceptar", "fecha válida",
        "fecha valida", "disponible", "futura", "no está disponible"
    ])
    asks_new_date = "?" in response
    forbidden = check_no_forbidden_phrases(response)
    role_ok = check_role_maintained(response)
    single_q = check_single_question(response)

    checks = {
        "Rechaza fecha pasada": (rejects_past_date, "No detectó rechazo claro de fecha pasada" if not rejects_past_date else None),
        "Solicita nueva fecha": (asks_new_date, None),
        "Una sola pregunta": (single_q, f"{response.count('?')} signos de pregunta" if not single_q else None),
        "Sin frases prohibidas": (len(forbidden) == 0, f"Encontradas: {forbidden}" if forbidden else None),
        "Mantiene rol de Laura": (role_ok, None),
    }
    return print_result(5, "Rechazo de fecha pasada — enero 2024", messages, response, checks)


# ── Main ────────────────────────────────────────────────────────────────────────
def main():
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise ValueError("La variable de entorno ANTHROPIC_API_KEY no está definida.")

    client = anthropic.Anthropic(api_key=api_key)
    system = load_system_prompt()

    print(f"\n{'█' * 70}")
    print(f"  SUITE DE PRUEBAS — LAURA 5.1 (Boats4U Cartagena)")
    print(f"  Modelo: {MODEL}")
    print(f"  System prompt: {SYSTEM_PROMPT_FILE.name} ({len(system)} chars)")
    print(f"{'█' * 70}")

    results = []
    scenarios = [
        scenario_1_activation,
        scenario_2_experience_selection,
        scenario_3_boat_recommendation,
        scenario_4_upsell_luxury,
        scenario_5_past_date_rejection,
    ]

    for scenario_fn in scenarios:
        try:
            passed = scenario_fn(client, system)
            results.append(passed)
        except Exception as e:
            print(f"\n❌ ERROR en {scenario_fn.__name__}: {e}")
            results.append(False)

    # Resumen final
    total = len(results)
    passed_count = sum(results)
    print(f"\n{'█' * 70}")
    print(f"  RESUMEN FINAL: {passed_count}/{total} escenarios aprobados")
    for i, r in enumerate(results, 1):
        print(f"  Escenario {i}: {'✅' if r else '❌'}")
    print(f"{'█' * 70}\n")

    if passed_count < total:
        exit(1)


if __name__ == "__main__":
    main()
