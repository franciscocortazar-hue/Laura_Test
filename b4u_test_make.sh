#!/bin/bash
# ============================================================
# B4U CRM FASE 2 — TEST SCRIPT MAKE
# Generado por LEO — CTO Proyecto Caribe Digital
# 24 Marzo 2026
#
# CÓMO USAR:
#   chmod +x b4u_test_make.sh
#   ./b4u_test_make.sh
#
# Cada grupo tiene pausa de 3s entre llamadas para no
# saturar los escenarios de Make.
# ============================================================

WEBHOOK_LEAD="https://hook.us2.make.com/svepg2mtc1qwqe3fw5l9jvm26amdsxvx"
WEBHOOK_COT="https://hook.us2.make.com/qx52sszmy6g57a3mt2v524ttdefqm64t"

echo ""
echo "============================================================"
echo " B4U CRM — TEST SUITE MAKE"
echo "============================================================"


# ============================================================
# GRUPO 1 — SUPERSEDED
# Mismo lead, 3 cotizaciones seguidas
# Resultado esperado:
#   - 3 cotizaciones en BD
#   - Solo la última en estado "sent"
#   - Las 2 anteriores en estado "superseded"
# ============================================================

echo ""
echo "------------------------------------------------------------"
echo " GRUPO 1 — SUPERSEDED (mismo lead, 3 cotizaciones)"
echo "------------------------------------------------------------"

echo ""
echo "[1.1] Registrar lead base para prueba superseded..."
RESP=$(curl -s -X POST "$WEBHOOK_LEAD" \
  -H "Content-Type: application/json" \
  -d '{
    "whatsapp_id": "+573132488737",
    "email": "francisco.cortazar@boats4u.co",
    "nombre_full": "Francisco Cortazar",
    "plan_id": "atardecer_bahia",
    "num_pax": 2,
    "fecha_salida": "2026-04-15",
    "idioma": "es",
    "hora_salida_real": "17:00:00"
  }')
echo "Response: $RESP"
LEAD_ID=$(echo $RESP | grep -o '"lead_id":"[^"]*"' | cut -d'"' -f4)
echo "Lead ID capturado: $LEAD_ID"
sleep 3

echo ""
echo "[1.2] Cotizacion #1 — bravo_290, baja..."
curl -s -X POST "$WEBHOOK_COT" \
  -H "Content-Type: application/json" \
  -d "{
    \"whatsapp_id\": \"+573132488737\",
    \"email\": \"francisco.cortazar@boats4u.co\",
    \"bote_id\": \"bravo_290\",
    \"lead_id\": \"$LEAD_ID\",
    \"plan_id\": \"atardecer_bahia\",
    \"num_pax\": 2,
    \"fecha_salida\": \"2026-04-15\",
    \"idioma\": \"es\",
    \"hora_salida_real\": \"17:00:00\",
    \"horas_extra\": 0
  }"
echo ""
sleep 4

echo ""
echo "[1.3] Cotizacion #2 — mismo lead, simula recotizacion..."
curl -s -X POST "$WEBHOOK_COT" \
  -H "Content-Type: application/json" \
  -d "{
    \"whatsapp_id\": \"+573132488737\",
    \"email\": \"francisco.cortazar@boats4u.co\",
    \"bote_id\": \"bravo_290\",
    \"lead_id\": \"$LEAD_ID\",
    \"plan_id\": \"atardecer_bahia\",
    \"num_pax\": 2,
    \"fecha_salida\": \"2026-04-15\",
    \"idioma\": \"es\",
    \"hora_salida_real\": \"17:00:00\",
    \"horas_extra\": 0
  }"
echo ""
sleep 4

echo ""
echo "[1.4] Cotizacion #3 — mismo lead, con hora extra..."
curl -s -X POST "$WEBHOOK_COT" \
  -H "Content-Type: application/json" \
  -d "{
    \"whatsapp_id\": \"+573132488737\",
    \"email\": \"francisco.cortazar@boats4u.co\",
    \"bote_id\": \"bravo_290\",
    \"lead_id\": \"$LEAD_ID\",
    \"plan_id\": \"atardecer_bahia\",
    \"num_pax\": 2,
    \"fecha_salida\": \"2026-04-15\",
    \"idioma\": \"es\",
    \"hora_salida_real\": \"17:00:00\",
    \"horas_extra\": 1
  }"
echo ""
sleep 3

echo ""
echo ">>> VERIFICAR EN SUPABASE — Grupo 1:"
echo "SELECT numero_cotizacion, estado_cotizacion, total_cotizado, horas_extra"
echo "FROM cotizaciones"
echo "WHERE lead_id = '$LEAD_ID'"
echo "ORDER BY created_at ASC;"
echo ""
echo "Esperado: 2 filas 'superseded', 1 fila 'sent' (la última)"


# ============================================================
# GRUPO 2 — PATCH LEAD + TEMPORADA ALTA
# Verificar status_lead = Cotizacion_Enviada
# y que temporada alta aplica correctamente (Semana Santa)
# ============================================================

echo ""
echo "------------------------------------------------------------"
echo " GRUPO 2 — PATCH LEAD + TEMPORADA ALTA (Semana Santa)"
echo "------------------------------------------------------------"

echo ""
echo "[2.1] Registrar lead — cliente nuevo, Semana Santa..."
RESP2=$(curl -s -X POST "$WEBHOOK_LEAD" \
  -H "Content-Type: application/json" \
  -d '{
    "whatsapp_id": "+573999000001",
    "email": "test.alta@boats4u.co",
    "nombre_full": "Test Temporada Alta",
    "plan_id": "atardecer_bahia",
    "num_pax": 2,
    "fecha_salida": "2026-04-02",
    "idioma": "es",
    "hora_salida_real": "17:00:00"
  }')
echo "Response: $RESP2"
LEAD_ID2=$(echo $RESP2 | grep -o '"lead_id":"[^"]*"' | cut -d'"' -f4)
echo "Lead ID: $LEAD_ID2"
sleep 3

echo ""
echo "[2.2] Cotizar — bravo_290, fecha Alta (2026-04-02)..."
curl -s -X POST "$WEBHOOK_COT" \
  -H "Content-Type: application/json" \
  -d "{
    \"whatsapp_id\": \"+573999000001\",
    \"email\": \"test.alta@boats4u.co\",
    \"bote_id\": \"bravo_290\",
    \"lead_id\": \"$LEAD_ID2\",
    \"plan_id\": \"atardecer_bahia\",
    \"num_pax\": 2,
    \"fecha_salida\": \"2026-04-02\",
    \"idioma\": \"es\",
    \"hora_salida_real\": \"17:00:00\",
    \"horas_extra\": 0
  }"
echo ""
sleep 3

echo ""
echo ">>> VERIFICAR EN SUPABASE — Grupo 2:"
echo "SELECT l.status_lead, l.bote_id, l.cotizacion_activa_id,"
echo "       c.estado_cotizacion, c.total_cotizado, c.temporada_aplicada"
echo "FROM leads l"
echo "LEFT JOIN cotizaciones c ON c.id = l.cotizacion_activa_id"
echo "WHERE l.whatsapp_id = '+573999000001';"
echo ""
echo "Esperado: status_lead='Cotizacion_Enviada', temporada_aplicada='alta', total=1.800.000"


# ============================================================
# GRUPO 3 — CLIENTES: variantes de identificación
# 3a: mismo WID, diferente email
# 3b: diferente WID, mismo email
# 3c: cliente completamente nuevo
# 3d: cliente en inglés
# ============================================================

echo ""
echo "------------------------------------------------------------"
echo " GRUPO 3 — VARIANTES DE CLIENTES"
echo "------------------------------------------------------------"

echo ""
echo "[3.1] Mismo WID, diferente email — debe usar cliente existente..."
curl -s -X POST "$WEBHOOK_LEAD" \
  -H "Content-Type: application/json" \
  -d '{
    "whatsapp_id": "+573132488737",
    "email": "otro.email@gmail.com",
    "nombre_full": "Francisco Cortazar",
    "plan_id": "atardecer_bahia",
    "num_pax": 4,
    "fecha_salida": "2026-04-20",
    "idioma": "es",
    "hora_salida_real": "17:00:00"
  }'
echo ""
sleep 3

echo ""
echo "[3.2] Diferente WID, mismo email — debe usar cliente existente por email..."
curl -s -X POST "$WEBHOOK_LEAD" \
  -H "Content-Type: application/json" \
  -d '{
    "whatsapp_id": "+573999000002",
    "email": "francisco.cortazar@boats4u.co",
    "nombre_full": "Francisco Cortazar Alt",
    "plan_id": "atardecer_bahia",
    "num_pax": 2,
    "fecha_salida": "2026-04-22",
    "idioma": "es",
    "hora_salida_real": "17:00:00"
  }'
echo ""
sleep 3

echo ""
echo "[3.3] Cliente completamente nuevo..."
curl -s -X POST "$WEBHOOK_LEAD" \
  -H "Content-Type: application/json" \
  -d '{
    "whatsapp_id": "+573999000003",
    "email": "nuevo.cliente@test.com",
    "nombre_full": "Cliente Nuevo Test",
    "plan_id": "atardecer_bahia",
    "num_pax": 3,
    "fecha_salida": "2026-04-25",
    "idioma": "es",
    "hora_salida_real": "17:00:00"
  }'
echo ""
sleep 3

echo ""
echo "[3.4] Cliente en inglés — idioma EN..."
RESP4=$(curl -s -X POST "$WEBHOOK_LEAD" \
  -H "Content-Type: application/json" \
  -d '{
    "whatsapp_id": "+13055550001",
    "email": "john.test@gmail.com",
    "nombre_full": "John Test",
    "plan_id": "atardecer_bahia",
    "num_pax": 2,
    "fecha_salida": "2026-04-15",
    "idioma": "en",
    "hora_salida_real": "17:00:00"
  }')
echo "Response: $RESP4"
LEAD_ID4=$(echo $RESP4 | grep -o '"lead_id":"[^"]*"' | cut -d'"' -f4)
sleep 3

echo ""
echo "[3.5] Cotizar cliente EN — bravo_290..."
curl -s -X POST "$WEBHOOK_COT" \
  -H "Content-Type: application/json" \
  -d "{
    \"whatsapp_id\": \"+13055550001\",
    \"email\": \"john.test@gmail.com\",
    \"bote_id\": \"bravo_290\",
    \"lead_id\": \"$LEAD_ID4\",
    \"plan_id\": \"atardecer_bahia\",
    \"num_pax\": 2,
    \"fecha_salida\": \"2026-04-15\",
    \"idioma\": \"en\",
    \"hora_salida_real\": \"17:00:00\",
    \"horas_extra\": 0
  }"
echo ""
sleep 3


# ============================================================
# GRUPO 4 — STRESS: grupo grande (15 pax → bravo_410)
# ============================================================

echo ""
echo "------------------------------------------------------------"
echo " GRUPO 4 — GRUPO GRANDE 15 PAX"
echo "------------------------------------------------------------"

echo ""
echo "[4.1] Registrar lead — 15 pax..."
RESP5=$(curl -s -X POST "$WEBHOOK_LEAD" \
  -H "Content-Type: application/json" \
  -d '{
    "whatsapp_id": "+573999000010",
    "email": "grupo.grande@test.com",
    "nombre_full": "Grupo Grande Test",
    "plan_id": "atardecer_bahia",
    "num_pax": 15,
    "fecha_salida": "2026-03-31",
    "idioma": "es",
    "hora_salida_real": "17:00:00"
  }')
echo "Response: $RESP5"
LEAD_ID5=$(echo $RESP5 | grep -o '"lead_id":"[^"]*"' | cut -d'"' -f4)
sleep 3

echo ""
echo "[4.2] Cotizar — bravo_410 (15 pax)..."
curl -s -X POST "$WEBHOOK_COT" \
  -H "Content-Type: application/json" \
  -d "{
    \"whatsapp_id\": \"+573999000010\",
    \"email\": \"grupo.grande@test.com\",
    \"bote_id\": \"bravo_410\",
    \"lead_id\": \"$LEAD_ID5\",
    \"plan_id\": \"atardecer_bahia\",
    \"num_pax\": 15,
    \"fecha_salida\": \"2026-03-31\",
    \"idioma\": \"es\",
    \"hora_salida_real\": \"17:00:00\",
    \"horas_extra\": 0
  }"
echo ""


# ============================================================
# SQL VERIFICACION FINAL
# ============================================================

echo ""
echo "============================================================"
echo " SQL VERIFICACION COMPLETA — Ejecutar en Supabase"
echo "============================================================"

echo ""
echo "-- Vista general de todos los tests:"
echo "SELECT c.whatsapp_id, c.nombre_full,"
echo "       l.status_lead, l.bote_id,"
echo "       cot.estado_cotizacion, cot.total_cotizado,"
echo "       cot.temporada_aplicada, cot.numero_cotizacion,"
echo "       cot.created_at"
echo "FROM clients c"
echo "JOIN leads l ON l.client_id = c.id"
echo "LEFT JOIN cotizaciones cot ON cot.id = l.cotizacion_activa_id"
echo "WHERE c.whatsapp_id IN ("
echo "  '+573132488737','+573999000001','+573999000002',"
echo "  '+573999000003','+13055550001','+573999000010'"
echo ")"
echo "ORDER BY cot.created_at DESC;"

echo ""
echo "-- Verificar superseded Grupo 1 (Francisco):"
echo "SELECT numero_cotizacion, estado_cotizacion, total_cotizado, horas_extra, created_at"
echo "FROM cotizaciones"
echo "WHERE lead_id IN (SELECT id FROM leads WHERE whatsapp_id = '+573132488737')"
echo "ORDER BY created_at ASC;"

echo ""
echo "-- Contar cotizaciones por estado:"
echo "SELECT estado_cotizacion, COUNT(*) as total"
echo "FROM cotizaciones"
echo "GROUP BY estado_cotizacion;"

echo ""
echo "============================================================"
echo " SQL LIMPIEZA — Ejecutar ANTES de re-correr el script"
echo "============================================================"
echo ""
echo "DELETE FROM cotizaciones WHERE lead_id IN (SELECT id FROM leads WHERE whatsapp_id IN ('+573132488737','+573999000001','+573999000002','+573999000003','+13055550001','+573999000010'));"
echo "DELETE FROM leads WHERE whatsapp_id IN ('+573132488737','+573999000001','+573999000002','+573999000003','+13055550001','+573999000010');"
echo "DELETE FROM clients WHERE whatsapp_id IN ('+573132488737','+573999000001','+573999000002','+573999000003','+13055550001','+573999000010');"

echo ""
echo "============================================================"
echo " TEST SUITE COMPLETO"
echo "============================================================"
echo ""
