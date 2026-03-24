#!/bin/bash
# ============================================================
# B4U CRM — TEST SUITE MAKE (7 ESCENARIOS)
# 24 Marzo 2026
#
# COMO USAR:
#   chmod +x b4u_test_make.sh
#   ./b4u_test_make.sh
#
# ESCENARIOS:
#   1. Cliente nuevo — flujo completo lead + cotización
#   2. Cliente recompra — mismo cliente, nuevo lead
#   3. Cliente datos errados — campos faltantes/inválidos
#   4. Una cotización simple — lead + 1 cotización limpia
#   5. Modificar cotización 5 veces — superseded stress
#   6. Cambio de plan mid-flow — cambia de bote y plan
#   7. Doble lead simultáneo — 2 leads casi al tiempo
# ============================================================

WEBHOOK_LEAD="https://hook.us2.make.com/svepg2mtc1qwqe3fw5l9jvm26amdsxvx"
WEBHOOK_COT="https://hook.us2.make.com/qx52sszmy6g57a3mt2v524ttdefqm64t"
WAIT=5  # segundos entre llamadas para que Make procese

echo ""
echo "============================================================"
echo " B4U CRM — TEST SUITE MAKE (7 ESCENARIOS)"
echo " $(date)"
echo "============================================================"


# ============================================================
# ESCENARIO 1 — CLIENTE NUEVO (flujo completo)
# Lead nuevo + 1 cotización
# Esperado:
#   - clients: 1 registro nuevo
#   - leads: status_lead = 'Cotizacion_Enviada'
#   - cotizaciones: 1 en estado 'sent'
# ============================================================

echo ""
echo "------------------------------------------------------------"
echo " ESCENARIO 1 — CLIENTE NUEVO (flujo completo)"
echo "------------------------------------------------------------"

echo "[1.1] Crear lead — Ana García, cliente nueva..."
curl -s -w "\nHTTP_CODE:%{http_code}" -X POST "$WEBHOOK_LEAD" \
  -H "Content-Type: application/json" \
  -d '{
    "whatsapp_id": "+573101000001",
    "email": "ana.garcia@test.com",
    "nombre_full": "Ana García",
    "source": "landing",
    "tipo_plan": "atardecer_bahia",
    "num_pax": 4,
    "fecha_salida": "2026-04-15",
    "idioma": "es",
    "payload": "{\"full_name\":\"Ana García\",\"plan\":\"atardecer_bahia\",\"preferred_date\":\"2026-04-15\",\"passengers\":4,\"email\":\"ana.garcia@test.com\",\"phone\":\"+573101000001\",\"language\":\"es\",\"source\":\"landing\"}"
  }'
echo ""
sleep $WAIT

echo "[1.2] Cotizar — bravo_290, temporada baja..."
curl -s -w "\nHTTP_CODE:%{http_code}" -X POST "$WEBHOOK_COT" \
  -H "Content-Type: application/json" \
  -d '{
    "whatsapp_id": "+573101000001",
    "email": "ana.garcia@test.com",
    "bote_id": "bravo_290",
    "plan_id": "atardecer_bahia",
    "num_pax": 4,
    "fecha_salida": "2026-04-15",
    "idioma": "es",
    "hora_salida_real": "17:00:00",
    "horas_extra": 0
  }'
echo ""
sleep $WAIT

echo ">>> VERIFICAR: 1 client, 1 lead (Cotizacion_Enviada), 1 cotización (sent)"


# ============================================================
# ESCENARIO 2 — CLIENTE RECOMPRA
# Mismo whatsapp_id de Ana, nueva fecha → nuevo lead
# Esperado:
#   - clients: NO crea duplicado (mismo client_id)
#   - leads: 2 leads para el mismo cliente
#   - cotizaciones: 1 por cada lead
# ============================================================

echo ""
echo "------------------------------------------------------------"
echo " ESCENARIO 2 — CLIENTE RECOMPRA (Ana vuelve a cotizar)"
echo "------------------------------------------------------------"

echo "[2.1] Nuevo lead — mismo WID, nueva fecha..."
curl -s -w "\nHTTP_CODE:%{http_code}" -X POST "$WEBHOOK_LEAD" \
  -H "Content-Type: application/json" \
  -d '{
    "whatsapp_id": "+573101000001",
    "email": "ana.garcia@test.com",
    "nombre_full": "Ana García",
    "source": "landing",
    "tipo_plan": "isla_del_sol",
    "num_pax": 6,
    "fecha_salida": "2026-05-10",
    "idioma": "es",
    "payload": "{\"full_name\":\"Ana García\",\"plan\":\"isla_del_sol\",\"preferred_date\":\"2026-05-10\",\"passengers\":6,\"email\":\"ana.garcia@test.com\",\"phone\":\"+573101000001\",\"language\":\"es\",\"source\":\"landing\"}"
  }'
echo ""
sleep $WAIT

echo "[2.2] Cotizar recompra — bravo_410, 6 pax..."
curl -s -w "\nHTTP_CODE:%{http_code}" -X POST "$WEBHOOK_COT" \
  -H "Content-Type: application/json" \
  -d '{
    "whatsapp_id": "+573101000001",
    "email": "ana.garcia@test.com",
    "bote_id": "bravo_410",
    "plan_id": "isla_del_sol",
    "num_pax": 6,
    "fecha_salida": "2026-05-10",
    "idioma": "es",
    "hora_salida_real": "10:00:00",
    "horas_extra": 0
  }'
echo ""
sleep $WAIT

echo ">>> VERIFICAR: 1 client (Ana), 2 leads, 2 cotizaciones"


# ============================================================
# ESCENARIO 3 — DATOS ERRADOS / INCOMPLETOS
# Campos faltantes, email mal, etc.
# Esperado:
#   - Make debe manejar errores sin crashear
#   - Puede crear lead con datos parciales o rechazar
# ============================================================

echo ""
echo "------------------------------------------------------------"
echo " ESCENARIO 3 — DATOS ERRADOS (campos faltantes/inválidos)"
echo "------------------------------------------------------------"

echo "[3.1] Sin email..."
curl -s -w "\nHTTP_CODE:%{http_code}" -X POST "$WEBHOOK_LEAD" \
  -H "Content-Type: application/json" \
  -d '{
    "whatsapp_id": "+573102000001",
    "email": "",
    "nombre_full": "Sin Email Test",
    "source": "landing",
    "tipo_plan": "atardecer_bahia",
    "num_pax": 2,
    "fecha_salida": "2026-04-20",
    "idioma": "es",
    "payload": "{\"full_name\":\"Sin Email Test\",\"plan\":\"atardecer_bahia\",\"preferred_date\":\"2026-04-20\",\"passengers\":2,\"email\":\"\",\"phone\":\"+573102000001\",\"language\":\"es\",\"source\":\"landing\"}"
  }'
echo ""
sleep $WAIT

echo "[3.2] Sin nombre..."
curl -s -w "\nHTTP_CODE:%{http_code}" -X POST "$WEBHOOK_LEAD" \
  -H "Content-Type: application/json" \
  -d '{
    "whatsapp_id": "+573102000002",
    "email": "sin.nombre@test.com",
    "nombre_full": "",
    "source": "landing",
    "tipo_plan": "atardecer_bahia",
    "num_pax": 2,
    "fecha_salida": "2026-04-20",
    "idioma": "es",
    "payload": "{\"full_name\":\"\",\"plan\":\"atardecer_bahia\",\"preferred_date\":\"2026-04-20\",\"passengers\":2,\"email\":\"sin.nombre@test.com\",\"phone\":\"+573102000002\",\"language\":\"es\",\"source\":\"landing\"}"
  }'
echo ""
sleep $WAIT

echo "[3.3] Sin whatsapp_id (campo obligatorio)..."
curl -s -w "\nHTTP_CODE:%{http_code}" -X POST "$WEBHOOK_LEAD" \
  -H "Content-Type: application/json" \
  -d '{
    "whatsapp_id": "",
    "email": "sin.wid@test.com",
    "nombre_full": "Sin WID Test",
    "source": "landing",
    "tipo_plan": "atardecer_bahia",
    "num_pax": 2,
    "fecha_salida": "2026-04-20",
    "idioma": "es",
    "payload": "{\"full_name\":\"Sin WID Test\",\"plan\":\"atardecer_bahia\",\"preferred_date\":\"2026-04-20\",\"passengers\":2,\"email\":\"sin.wid@test.com\",\"phone\":\"\",\"language\":\"es\",\"source\":\"landing\"}"
  }'
echo ""
sleep $WAIT

echo "[3.4] Num_pax = 0 (inválido)..."
curl -s -w "\nHTTP_CODE:%{http_code}" -X POST "$WEBHOOK_LEAD" \
  -H "Content-Type: application/json" \
  -d '{
    "whatsapp_id": "+573102000003",
    "email": "cero.pax@test.com",
    "nombre_full": "Cero Pax Test",
    "source": "landing",
    "tipo_plan": "atardecer_bahia",
    "num_pax": 0,
    "fecha_salida": "2026-04-20",
    "idioma": "es",
    "payload": "{\"full_name\":\"Cero Pax Test\",\"plan\":\"atardecer_bahia\",\"preferred_date\":\"2026-04-20\",\"passengers\":0,\"email\":\"cero.pax@test.com\",\"phone\":\"+573102000003\",\"language\":\"es\",\"source\":\"landing\"}"
  }'
echo ""
sleep $WAIT

echo ">>> VERIFICAR: Make no crashea. Revisar qué registros creó y cuáles rechazó."


# ============================================================
# ESCENARIO 4 — UNA COTIZACIÓN SIMPLE (happy path limpio)
# Lead + 1 sola cotización, sin complicaciones
# Esperado:
#   - 1 client, 1 lead, 1 cotización
#   - Todo en estado correcto
# ============================================================

echo ""
echo "------------------------------------------------------------"
echo " ESCENARIO 4 — COTIZACIÓN SIMPLE (happy path)"
echo "------------------------------------------------------------"

echo "[4.1] Lead — Carlos Mendez..."
curl -s -w "\nHTTP_CODE:%{http_code}" -X POST "$WEBHOOK_LEAD" \
  -H "Content-Type: application/json" \
  -d '{
    "whatsapp_id": "+573103000001",
    "email": "carlos.mendez@test.com",
    "nombre_full": "Carlos Mendez",
    "source": "landing",
    "tipo_plan": "isla_del_sol",
    "num_pax": 2,
    "fecha_salida": "2026-04-18",
    "idioma": "es",
    "payload": "{\"full_name\":\"Carlos Mendez\",\"plan\":\"isla_del_sol\",\"preferred_date\":\"2026-04-18\",\"passengers\":2,\"email\":\"carlos.mendez@test.com\",\"phone\":\"+573103000001\",\"language\":\"es\",\"source\":\"landing\"}"
  }'
echo ""
sleep $WAIT

echo "[4.2] Cotización única — bravo_290..."
curl -s -w "\nHTTP_CODE:%{http_code}" -X POST "$WEBHOOK_COT" \
  -H "Content-Type: application/json" \
  -d '{
    "whatsapp_id": "+573103000001",
    "email": "carlos.mendez@test.com",
    "bote_id": "bravo_290",
    "plan_id": "isla_del_sol",
    "num_pax": 2,
    "fecha_salida": "2026-04-18",
    "idioma": "es",
    "hora_salida_real": "10:00:00",
    "horas_extra": 0
  }'
echo ""
sleep $WAIT

echo ">>> VERIFICAR: 1 client, 1 lead (Cotizacion_Enviada), 1 cotización (sent)"


# ============================================================
# ESCENARIO 5 — MODIFICAR COTIZACIÓN 5 VECES (superseded stress)
# Mismo lead, 5 cotizaciones seguidas
# Esperado:
#   - 5 cotizaciones en BD
#   - 4 en estado 'superseded'
#   - 1 (la última) en estado 'sent'
#   - lead.cotizacion_activa_id = la última
# ============================================================

echo ""
echo "------------------------------------------------------------"
echo " ESCENARIO 5 — 5 COTIZACIONES SEGUIDAS (superseded stress)"
echo "------------------------------------------------------------"

echo "[5.1] Lead — María López..."
curl -s -w "\nHTTP_CODE:%{http_code}" -X POST "$WEBHOOK_LEAD" \
  -H "Content-Type: application/json" \
  -d '{
    "whatsapp_id": "+573104000001",
    "email": "maria.lopez@test.com",
    "nombre_full": "María López",
    "source": "landing",
    "tipo_plan": "atardecer_bahia",
    "num_pax": 2,
    "fecha_salida": "2026-04-20",
    "idioma": "es",
    "payload": "{\"full_name\":\"María López\",\"plan\":\"atardecer_bahia\",\"preferred_date\":\"2026-04-20\",\"passengers\":2,\"email\":\"maria.lopez@test.com\",\"phone\":\"+573104000001\",\"language\":\"es\",\"source\":\"landing\"}"
  }'
echo ""
sleep $WAIT

echo "[5.2] Cotización #1 — bravo_290, 2 pax, 0 horas extra..."
curl -s -w "\nHTTP_CODE:%{http_code}" -X POST "$WEBHOOK_COT" \
  -H "Content-Type: application/json" \
  -d '{
    "whatsapp_id": "+573104000001",
    "email": "maria.lopez@test.com",
    "bote_id": "bravo_290",
    "plan_id": "atardecer_bahia",
    "num_pax": 2,
    "fecha_salida": "2026-04-20",
    "idioma": "es",
    "hora_salida_real": "17:00:00",
    "horas_extra": 0
  }'
echo ""
sleep $WAIT

echo "[5.3] Cotización #2 — cambia a 4 pax..."
curl -s -w "\nHTTP_CODE:%{http_code}" -X POST "$WEBHOOK_COT" \
  -H "Content-Type: application/json" \
  -d '{
    "whatsapp_id": "+573104000001",
    "email": "maria.lopez@test.com",
    "bote_id": "bravo_290",
    "plan_id": "atardecer_bahia",
    "num_pax": 4,
    "fecha_salida": "2026-04-20",
    "idioma": "es",
    "hora_salida_real": "17:00:00",
    "horas_extra": 0
  }'
echo ""
sleep $WAIT

echo "[5.4] Cotización #3 — agrega 1 hora extra..."
curl -s -w "\nHTTP_CODE:%{http_code}" -X POST "$WEBHOOK_COT" \
  -H "Content-Type: application/json" \
  -d '{
    "whatsapp_id": "+573104000001",
    "email": "maria.lopez@test.com",
    "bote_id": "bravo_290",
    "plan_id": "atardecer_bahia",
    "num_pax": 4,
    "fecha_salida": "2026-04-20",
    "idioma": "es",
    "hora_salida_real": "17:00:00",
    "horas_extra": 1
  }'
echo ""
sleep $WAIT

echo "[5.5] Cotización #4 — cambia fecha a Semana Santa (alta)..."
curl -s -w "\nHTTP_CODE:%{http_code}" -X POST "$WEBHOOK_COT" \
  -H "Content-Type: application/json" \
  -d '{
    "whatsapp_id": "+573104000001",
    "email": "maria.lopez@test.com",
    "bote_id": "bravo_290",
    "plan_id": "atardecer_bahia",
    "num_pax": 4,
    "fecha_salida": "2026-04-02",
    "idioma": "es",
    "hora_salida_real": "17:00:00",
    "horas_extra": 1
  }'
echo ""
sleep $WAIT

echo "[5.6] Cotización #5 — cambia a bravo_410, 2 horas extra..."
curl -s -w "\nHTTP_CODE:%{http_code}" -X POST "$WEBHOOK_COT" \
  -H "Content-Type: application/json" \
  -d '{
    "whatsapp_id": "+573104000001",
    "email": "maria.lopez@test.com",
    "bote_id": "bravo_410",
    "plan_id": "atardecer_bahia",
    "num_pax": 4,
    "fecha_salida": "2026-04-02",
    "idioma": "es",
    "hora_salida_real": "17:00:00",
    "horas_extra": 2
  }'
echo ""
sleep $WAIT

echo ">>> VERIFICAR: 5 cotizaciones — 4 superseded, 1 sent (la última)"


# ============================================================
# ESCENARIO 6 — CAMBIO DE PLAN MID-FLOW
# Lead con un plan, cotiza otro plan diferente
# Esperado:
#   - Lead se actualiza con el nuevo plan/bote
#   - Cotización refleja el plan correcto
# ============================================================

echo ""
echo "------------------------------------------------------------"
echo " ESCENARIO 6 — CAMBIO DE PLAN MID-FLOW"
echo "------------------------------------------------------------"

echo "[6.1] Lead — Pedro Ruiz, pide atardecer_bahia..."
curl -s -w "\nHTTP_CODE:%{http_code}" -X POST "$WEBHOOK_LEAD" \
  -H "Content-Type: application/json" \
  -d '{
    "whatsapp_id": "+573105000001",
    "email": "pedro.ruiz@test.com",
    "nombre_full": "Pedro Ruiz",
    "source": "landing",
    "tipo_plan": "atardecer_bahia",
    "num_pax": 2,
    "fecha_salida": "2026-04-25",
    "idioma": "es",
    "payload": "{\"full_name\":\"Pedro Ruiz\",\"plan\":\"atardecer_bahia\",\"preferred_date\":\"2026-04-25\",\"passengers\":2,\"email\":\"pedro.ruiz@test.com\",\"phone\":\"+573105000001\",\"language\":\"es\",\"source\":\"landing\"}"
  }'
echo ""
sleep $WAIT

echo "[6.2] Cotiza atardecer_bahia primero..."
curl -s -w "\nHTTP_CODE:%{http_code}" -X POST "$WEBHOOK_COT" \
  -H "Content-Type: application/json" \
  -d '{
    "whatsapp_id": "+573105000001",
    "email": "pedro.ruiz@test.com",
    "bote_id": "bravo_290",
    "plan_id": "atardecer_bahia",
    "num_pax": 2,
    "fecha_salida": "2026-04-25",
    "idioma": "es",
    "hora_salida_real": "17:00:00",
    "horas_extra": 0
  }'
echo ""
sleep $WAIT

echo "[6.3] Cambia a isla_del_sol con bote más grande..."
curl -s -w "\nHTTP_CODE:%{http_code}" -X POST "$WEBHOOK_COT" \
  -H "Content-Type: application/json" \
  -d '{
    "whatsapp_id": "+573105000001",
    "email": "pedro.ruiz@test.com",
    "bote_id": "bravo_410",
    "plan_id": "isla_del_sol",
    "num_pax": 8,
    "fecha_salida": "2026-04-25",
    "idioma": "es",
    "hora_salida_real": "10:00:00",
    "horas_extra": 0
  }'
echo ""
sleep $WAIT

echo ">>> VERIFICAR: 2 cotizaciones — 1ra superseded (atardecer), 2da sent (isla_del_sol)"


# ============================================================
# ESCENARIO 7 — DOBLE LEAD RÁPIDO (race condition)
# 2 leads con WIDs diferentes, casi simultáneos
# Esperado:
#   - Make procesa ambos sin errores
#   - 2 clients, 2 leads independientes
# ============================================================

echo ""
echo "------------------------------------------------------------"
echo " ESCENARIO 7 — DOBLE LEAD RÁPIDO (race condition)"
echo "------------------------------------------------------------"

echo "[7.1] Lead A — enviando..."
curl -s -w "\nHTTP_CODE:%{http_code}" -X POST "$WEBHOOK_LEAD" \
  -H "Content-Type: application/json" \
  -d '{
    "whatsapp_id": "+573106000001",
    "email": "lead.a@test.com",
    "nombre_full": "Lead A Rápido",
    "source": "landing",
    "tipo_plan": "atardecer_bahia",
    "num_pax": 2,
    "fecha_salida": "2026-04-28",
    "idioma": "es",
    "payload": "{\"full_name\":\"Lead A Rápido\",\"plan\":\"atardecer_bahia\",\"preferred_date\":\"2026-04-28\",\"passengers\":2,\"email\":\"lead.a@test.com\",\"phone\":\"+573106000001\",\"language\":\"es\",\"source\":\"landing\"}"
  }' &

echo "[7.2] Lead B — enviando (simultáneo)..."
curl -s -w "\nHTTP_CODE:%{http_code}" -X POST "$WEBHOOK_LEAD" \
  -H "Content-Type: application/json" \
  -d '{
    "whatsapp_id": "+573106000002",
    "email": "lead.b@test.com",
    "nombre_full": "Lead B Rápido",
    "source": "landing",
    "tipo_plan": "isla_del_sol",
    "num_pax": 3,
    "fecha_salida": "2026-04-28",
    "idioma": "es",
    "payload": "{\"full_name\":\"Lead B Rápido\",\"plan\":\"isla_del_sol\",\"preferred_date\":\"2026-04-28\",\"passengers\":3,\"email\":\"lead.b@test.com\",\"phone\":\"+573106000002\",\"language\":\"es\",\"source\":\"landing\"}"
  }' &

wait
echo ""
sleep $WAIT

echo ">>> VERIFICAR: 2 clients, 2 leads — sin duplicados, sin errores"


# ============================================================
# SQL VERIFICACIÓN FINAL
# ============================================================

echo ""
echo "============================================================"
echo " SQL VERIFICACIÓN — Copiar y pegar en Supabase"
echo "============================================================"

cat << 'SQLEOF'

-- 1. Vista general de TODOS los escenarios:
SELECT c.whatsapp_id, c.nombre_full,
       l.status_lead, l.bote_id,
       cot.estado_cotizacion, cot.total_cotizado,
       cot.temporada_aplicada, cot.plan_id,
       cot.num_pax, cot.horas_extra
FROM clients c
JOIN leads l ON l.client_id = c.id
LEFT JOIN cotizaciones cot ON cot.id = l.cotizacion_activa_id
ORDER BY c.whatsapp_id, l.created_at;

-- 2. Escenario 2 (recompra): ¿Ana tiene 1 solo client pero 2 leads?
SELECT c.id as client_id, c.whatsapp_id, c.nombre_full,
       l.id as lead_id, l.status_lead, l.bote_id
FROM clients c
JOIN leads l ON l.client_id = c.id
WHERE c.whatsapp_id = '+573101000001';

-- 3. Escenario 5 (superseded stress): 5 cotizaciones, 4 superseded
SELECT numero_cotizacion, estado_cotizacion, total_cotizado,
       num_pax, horas_extra, bote_id, fecha_salida, temporada_aplicada
FROM cotizaciones
WHERE whatsapp_id = '+573104000001'
ORDER BY created_at ASC;

-- 4. Conteo por estado:
SELECT estado_cotizacion, COUNT(*) as total
FROM cotizaciones
GROUP BY estado_cotizacion;

-- 5. Conteo general:
SELECT 'clients' as tabla, COUNT(*) as total FROM clients
UNION ALL
SELECT 'leads', COUNT(*) FROM leads
UNION ALL
SELECT 'cotizaciones', COUNT(*) FROM cotizaciones;

SQLEOF

echo ""
echo "============================================================"
echo " SQL LIMPIEZA (para re-correr)"
echo "============================================================"

cat << 'SQLEOF'

DELETE FROM cotizaciones;
DELETE FROM leads;
DELETE FROM clients;

SQLEOF

echo ""
echo "============================================================"
echo " TEST SUITE COMPLETO — $(date)"
echo "============================================================"
echo ""
