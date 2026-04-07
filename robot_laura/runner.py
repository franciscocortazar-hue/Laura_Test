"""
Robot Laura — runner.py
Uso: python runner.py
Requiere: pip install requests
Configurar: export SUPABASE_SERVICE_ROLE_KEY="tu_key"
"""

import json, time, requests, os
from datetime import datetime
from pathlib import Path

SUPABASE_URL = "https://gqofyvvbmqnxpsgtwudq.supabase.co"
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")

WEBHOOKS = {
    "REGISTRAR_LEAD":           "https://hook.us2.make.com/svepg2mtc1qwqe3fw5l9jvm26amdsxvx",
    "COMPLETAR_BOTE_Y_COTIZAR": "https://hook.us2.make.com/qx52sszmy6g57a3mt2v524ttdefqm64t"
}

SCENARIOS_DIR = Path(__file__).parent / "scenarios"
REPORTS_DIR   = Path(__file__).parent / "reports"
REPORTS_DIR.mkdir(exist_ok=True)

def sb_headers():
    return {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}

def sb_query(tabla, filtro):
    r = requests.get(f"{SUPABASE_URL}/rest/v1/{tabla}?{filtro}", headers=sb_headers())
    return r.json() if r.status_code == 200 else []

def sb_delete(tabla, filtro):
    requests.delete(f"{SUPABASE_URL}/rest/v1/{tabla}?{filtro}", headers=sb_headers())

def cleanup(wid):
    if not wid: return
    print(f"  Limpiando WID {wid}...")
    # borrar cotizaciones del lead
    leads = sb_query("leads", f"whatsapp_id=eq.{wid}&select=id")
    if leads:
        ids = ",".join(f'"{l["id"]}"' for l in leads)
        sb_delete("cotizaciones", f"lead_id=in.({ids})")
    sb_delete("leads",   f"whatsapp_id=eq.{wid}")
    sb_delete("clients", f"whatsapp_id=eq.{wid}")

def fire_webhook(key, payload):
    r = requests.post(WEBHOOKS[key], json=payload, timeout=30)
    return r.status_code, r.text[:200]

def get_lead_id(wid):
    rows = sb_query("leads", f"whatsapp_id=eq.{wid}&order=created_at.desc&limit=1")
    return rows[0]["id"] if rows else None

def check(a, lead_id):
    filtro = a.get("filtro","").replace("[LEAD_ID_T01]", lead_id or "") \
                                .replace("[LEAD_ID_T06]", lead_id or "") \
                                .replace("[LEAD_ID_T07]", lead_id or "")
    if a.get("tipo") == "http_status":
        return None, "verificacion manual"
    rows = sb_query(a["tabla"], filtro)
    if a.get("campo") == "COUNT":
        real = len(rows)
        return real == a["esperado"], f"COUNT={real} (esperado={a['esperado']})"
    if not rows:
        return False, f"Sin resultados — {a['tabla']} filtro={filtro}"
    real = rows[0].get(a["campo"])
    if a.get("tipo_check") == "mayor_que":
        ok = real is not None and float(real) > a["esperado"]
    else:
        ok = str(real) == str(a["esperado"])
    return ok, f"{a['campo']}={real} (esperado={a['esperado']})"

def run(sc):
    print(f"\n{'='*55}\n{sc['id']} — {sc['nombre']}")
    c = sc.get("cleanup") or {}
    if isinstance(c, dict): cleanup(c.get("borrar_wid"))
    pre = sc.get("pre_payload")
    if pre:
        print(f"  Pre-req: {pre['webhook']}")
        fire_webhook(pre["webhook"], pre["payload"])
        time.sleep(4)
    print(f"  POST {sc['webhook']}")
    t0 = time.time()
    status, resp = fire_webhook(sc["webhook"], sc["payload"])
    elapsed = time.time() - t0
    print(f"  HTTP {status} — {elapsed:.1f}s — {resp}")
    wait = sc.get("espera_segundos", 5)
    print(f"  Esperando {wait}s...")
    time.sleep(wait)
    wid = sc["payload"].get("whatsapp_id","")
    lead_id = get_lead_id(wid)
    results = []
    for a in sc.get("assertions", []):
        ok, detail = check(a, lead_id)
        icon = "OK" if ok else ("--" if ok is None else "FAIL")
        print(f"  [{icon}] {a.get('descripcion', a.get('campo',''))}: {detail}")
        results.append({"ok": ok, "desc": a.get("descripcion",""), "detail": detail})
    passed = all(r["ok"] is not False for r in results)
    print(f"  => {'PASS' if passed else 'FAIL'}")
    return {"id": sc["id"], "nombre": sc["nombre"], "passed": passed,
            "results": results, "http": status, "elapsed": elapsed}

def main():
    if not SUPABASE_KEY or SUPABASE_KEY == "":
        print("ERROR: configurar SUPABASE_SERVICE_ROLE_KEY")
        print("  export SUPABASE_SERVICE_ROLE_KEY='tu_key'")
        exit(1)
    scenarios = sorted(SCENARIOS_DIR.glob("CODE_*.json"))
    if not scenarios:
        print("No hay escenarios CODE_*.json en scenarios/")
        exit(1)
    all_results = []
    for path in scenarios:
        sc = json.loads(path.read_text())
        all_results.append(run(sc))
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    report = REPORTS_DIR / f"reporte_code_{ts}.md"
    passed = sum(1 for r in all_results if r["passed"])
    total  = len(all_results)
    lines  = [f"# Reporte Robot Laura — Code — {datetime.now():%Y-%m-%d %H:%M}","",
              "## Resumen", f"- Total: {total}", f"- PASS: {passed}",
              f"- FAIL: {total-passed}", f"- Tasa: {int(passed/total*100)}%","","## Detalle",""]
    for r in all_results:
        icon = "PASS" if r["passed"] else "FAIL"
        lines.append(f"### {r['id']} — {r['nombre']} [{icon}]")
        lines.append(f"HTTP: {r['http']} | Tiempo: {r['elapsed']:.1f}s")
        for a in r["results"]:
            lines.append(f"  - {'OK' if a['ok'] else 'FAIL'}: {a['desc']} — {a['detail']}")
        lines.append("")
    report.write_text("\n".join(lines))
    print(f"\nReporte: {report}")
    print(f"Resultado: {passed}/{total} PASS")

if __name__ == "__main__":
    main()
