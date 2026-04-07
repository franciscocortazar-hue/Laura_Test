"""
Robot Laura — runner.py
Claude Code ejecuta: python runner.py
Requiere: pip install requests

Limpieza de base de datos:
  - cleanup() respeta FK: borra cotizaciones -> leads -> clients
  - ANTES de la corrida: limpia TODOS los WIDs de prueba
  - DESPUES de la corrida: limpia TODOS los WIDs de prueba (siempre, incluso con error)
"""
import json, time, requests, os
from datetime import datetime
from pathlib import Path

SUPABASE_URL = "https://gqofyvvbmqnxpsgtwudq.supabase.co"
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "PEGAR_AQUI")

WEBHOOKS = {
    "REGISTRAR_LEAD":           "https://hook.us2.make.com/svepg2mtc1qwqe3fw5l9jvm26amdsxvx",
    "COMPLETAR_BOTE_Y_COTIZAR": "https://hook.us2.make.com/qx52sszmy6g57a3mt2v524ttdefqm64t"
}

# WIDs de prueba que usan los escenarios CODE_*
TEST_WIDS = [
    "+17809990001",  # T01, T03, T05, T09
    "+17809990002",  # T02
    "+17809990004",  # T04
    "+17809990006",  # T06, T08
    "+17809990007",  # T07
]

SCENARIOS_DIR = Path("scenarios")
REPORTS_DIR   = Path("reports")
REPORTS_DIR.mkdir(exist_ok=True)

def sb_headers():
    return {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}

def sb_query(tabla, filtro):
    r = requests.get(f"{SUPABASE_URL}/rest/v1/{tabla}?{filtro}", headers=sb_headers())
    return r.json() if r.status_code == 200 else []

def sb_delete(tabla, filtro):
    requests.delete(f"{SUPABASE_URL}/rest/v1/{tabla}?{filtro}", headers=sb_headers())

def cleanup(wid):
    """Borra cotizaciones, leads y clients de un WID respetando la FK."""
    if not wid: return
    print(f"  🧹 Limpiando WID {wid}")
    # 1) Buscar leads del WID y borrar sus cotizaciones primero (FK)
    leads = sb_query("leads", f"whatsapp_id=eq.{wid}&select=id")
    if leads:
        ids = ",".join(f'"{l["id"]}"' for l in leads)
        sb_delete("cotizaciones", f"lead_id=in.({ids})")
    # 2) Borrar leads
    sb_delete("leads",   f"whatsapp_id=eq.{wid}")
    # 3) Borrar clients
    sb_delete("clients", f"whatsapp_id=eq.{wid}")

def cleanup_all_test_data(label=""):
    """Limpia TODOS los WIDs de prueba. Se llama antes y despues de la corrida."""
    print(f"\n{'='*55}")
    print(f"🧹 Limpieza {label} corrida — {len(TEST_WIDS)} WIDs de prueba")
    print(f"{'='*55}")
    for wid in TEST_WIDS:
        cleanup(wid)
    print(f"✅ Limpieza {label} corrida completa")

def fire(webhook_key, payload):
    r = requests.post(WEBHOOKS[webhook_key], json=payload, timeout=30)
    return r.status_code, r.text

def resolve_lead_id(wid):
    rows = sb_query("leads", f"whatsapp_id=eq.{wid}&order=created_at.desc&limit=1")
    return rows[0]["id"] if rows else None

def check(a, lead_id=None):
    filtro = a.get("filtro","").replace("[LEAD_ID]", lead_id or "")
    if a.get("tipo") == "http_status": return None, "manual"
    rows = sb_query(a["tabla"], filtro)
    if a.get("campo") == "COUNT":
        real = len(rows)
        return real == a["esperado"], f"COUNT={real} (esperado={a['esperado']})"
    if not rows: return False, f"Sin resultados — {a['tabla']}?{filtro}"
    real = rows[0].get(a["campo"])
    if a.get("tipo_check") == "mayor_que":
        ok = real is not None and float(real) > a["esperado"]
    else:
        ok = str(real) == str(a["esperado"])
    return ok, f"{a['campo']}={real} (esperado={a['esperado']})"

def run(sc):
    print(f"\n{'='*55}\n▶ {sc['id']} — {sc['nombre']}")
    wid_clean = (sc.get("cleanup") or {}).get("borrar_wid")
    cleanup(wid_clean)
    pre = sc.get("pre_payload")
    if pre:
        print(f"  ⚙️  Pre: {pre['webhook']}")
        fire(pre["webhook"], pre["payload"])
        time.sleep(4)
    print(f"  🚀 POST → {sc['webhook']}")
    t0 = time.time()
    status, resp = fire(sc["webhook"], sc["payload"])
    elapsed = time.time() - t0
    print(f"  ↩  HTTP {status} — {elapsed:.1f}s")
    wait = sc.get("espera_segundos", 5)
    print(f"  ⏳ Esperando {wait}s...")
    time.sleep(wait)
    lead_id = resolve_lead_id(sc["payload"].get("whatsapp_id",""))
    results = []
    for a in sc.get("assertions", []):
        ok, detail = check(a, lead_id)
        icon = "✅" if ok else ("⚠️" if ok is None else "❌")
        print(f"  {icon} {a.get('descripcion', a.get('campo',''))}: {detail}")
        results.append({"ok": ok, "desc": a.get("descripcion",""), "detail": detail})
    passed = all(r["ok"] is not False for r in results)
    print(f"  {'✅ PASS' if passed else '❌ FAIL'}")
    return {"id": sc["id"], "nombre": sc["nombre"], "passed": passed,
            "results": results, "status": status, "elapsed": elapsed}

def main():
    if SUPABASE_KEY == "PEGAR_AQUI":
        print("❌ Configura: export SUPABASE_SERVICE_ROLE_KEY=tu_key")
        return
    scenarios = sorted(SCENARIOS_DIR.glob("CODE_*.json"))
    if not scenarios:
        print("❌ No hay escenarios en scenarios/CODE_*.json")
        return

    # Limpieza ANTES de la corrida — base en estado limpio
    cleanup_all_test_data("ANTES de la")

    try:
        all_results = [run(json.loads(p.read_text())) for p in scenarios]
        passed = sum(1 for r in all_results if r["passed"])
        total  = len(all_results)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        report = REPORTS_DIR / f"reporte_code_{ts}.md"
        lines = [f"# Reporte Robot Laura — Code — {datetime.now().strftime('%Y-%m-%d %H:%M')}",
                 "", f"## Resumen: {passed}/{total} PASS ({int(passed/total*100)}%)", ""]
        for r in all_results:
            icon = "✅" if r["passed"] else "❌"
            lines += [f"### {r['id']} — {r['nombre']} {icon}",
                      f"- HTTP {r['status']} — {r['elapsed']:.1f}s"]
            for a in r["results"]:
                aicon = "✅" if a["ok"] else ("⚠️" if a["ok"] is None else "❌")
                lines.append(f"  - {aicon} {a['desc']}: {a['detail']}")
            lines.append("")
        report.write_text("\n".join(lines))
        print(f"\n📄 Reporte: {report}\n🏁 {passed}/{total} PASS")
    finally:
        # Limpieza DESPUES — siempre, incluso si fallo algo en el medio
        cleanup_all_test_data("DESPUES de la")

if __name__ == "__main__":
    main()
