#!/bin/bash
WEBHOOK_LEAD="https://hook.us2.make.com/svepg2mtc1qwqe3fw5l9jvm26amdsxvx"
WEBHOOK_COT="https://hook.us2.make.com/qx52sszmy6g57a3mt2v524ttdefqm64t"

reg() {
  curl -s -X POST "$WEBHOOK_LEAD" -H "Content-Type: application/json" -d "$1" | grep -o '"lead_id":"[^"]*"' | grep -o '[^"]*$' | grep -o '^[^"]*'
}

cot() {
  echo ""
  curl -s -X POST "$WEBHOOK_COT" -H "Content-Type: application/json" -d "$1"
  echo ""
}

echo "=== LIMPIANDO DATOS PREVIOS ==="
echo "Asegurate de haber corrido DELETE en Supabase antes de este script"
echo ""

echo "=== ESCENARIO A - REGISTRO 5 CLIENTES ==="
L1=$(reg '{"whatsapp_id":"+573100000001","email":"cliente1@test.com","nombre_full":"Cliente Uno","plan_id":"atardecer_bahia","num_pax":2,"fecha_salida":"2026-04-15","idioma":"es","hora_salida_real":"17:00:00","source":"landing"}')
echo "L1: $L1"; sleep 3
L2=$(reg '{"whatsapp_id":"+573100000002","email":"cliente2@test.com","nombre_full":"Cliente Dos","plan_id":"atardecer_bahia","num_pax":3,"fecha_salida":"2026-04-16","idioma":"es","hora_salida_real":"17:00:00","source":"landing"}')
echo "L2: $L2"; sleep 3
L3=$(reg '{"whatsapp_id":"+573100000003","email":"cliente3@test.com","nombre_full":"Cliente Tres","plan_id":"atardecer_bahia","num_pax":4,"fecha_salida":"2026-04-17","idioma":"es","hora_salida_real":"17:00:00","source":"landing"}')
echo "L3: $L3"; sleep 3
L4=$(reg '{"whatsapp_id":"+573100000004","email":"cliente4@test.com","nombre_full":"Cliente Cuatro","plan_id":"atardecer_bahia","num_pax":5,"fecha_salida":"2026-04-18","idioma":"es","hora_salida_real":"17:00:00","source":"landing"}')
echo "L4: $L4"; sleep 3
L5=$(reg '{"whatsapp_id":"+573100000005","email":"cliente5@test.com","nombre_full":"Cliente Cinco","plan_id":"atardecer_bahia","num_pax":6,"fecha_salida":"2026-04-19","idioma":"es","hora_salida_real":"17:00:00","source":"landing"}')
echo "L5: $L5"; sleep 3

echo ""
echo "=== ESCENARIO A - COTIZACIONES ==="
cot "{\"whatsapp_id\":\"+573100000001\",\"email\":\"cliente1@test.com\",\"bote_id\":\"bravo_290\",\"lead_id\":\"$L1\",\"plan_id\":\"atardecer_bahia\",\"num_pax\":2,\"fecha_salida\":\"2026-04-15\",\"idioma\":\"es\",\"hora_salida_real\":\"17:00:00\",\"horas_extra\":0}"; sleep 5
cot "{\"whatsapp_id\":\"+573100000002\",\"email\":\"cliente2@test.com\",\"bote_id\":\"bravo_300\",\"lead_id\":\"$L2\",\"plan_id\":\"atardecer_bahia\",\"num_pax\":3,\"fecha_salida\":\"2026-04-16\",\"idioma\":\"es\",\"hora_salida_real\":\"17:00:00\",\"horas_extra\":0}"; sleep 5
cot "{\"whatsapp_id\":\"+573100000003\",\"email\":\"cliente3@test.com\",\"bote_id\":\"firpol_34\",\"lead_id\":\"$L3\",\"plan_id\":\"atardecer_bahia\",\"num_pax\":4,\"fecha_salida\":\"2026-04-17\",\"idioma\":\"es\",\"hora_salida_real\":\"17:00:00\",\"horas_extra\":0}"; sleep 5
cot "{\"whatsapp_id\":\"+573100000004\",\"email\":\"cliente4@test.com\",\"bote_id\":\"bravo_380\",\"lead_id\":\"$L4\",\"plan_id\":\"atardecer_bahia\",\"num_pax\":5,\"fecha_salida\":\"2026-04-18\",\"idioma\":\"es\",\"hora_salida_real\":\"17:00:00\",\"horas_extra\":0}"; sleep 5
cot "{\"whatsapp_id\":\"+573100000005\",\"email\":\"cliente5@test.com\",\"bote_id\":\"bravo_410\",\"lead_id\":\"$L5\",\"plan_id\":\"atardecer_bahia\",\"num_pax\":6,\"fecha_salida\":\"2026-04-19\",\"idioma\":\"es\",\"hora_salida_real\":\"17:00:00\",\"horas_extra\":0}"; sleep 5

echo ""
echo "=== ESCENARIO B - CLIENTE NUEVO 5 BOTES SUPERSEDED ==="
LB=$(reg '{"whatsapp_id":"+573400000001","email":"superseded@test.com","nombre_full":"Cliente Superseded","plan_id":"atardecer_bahia","num_pax":10,"fecha_salida":"2026-04-15","idioma":"es","hora_salida_real":"17:00:00","source":"landing"}')
echo "LB: $LB"; sleep 4

cot "{\"whatsapp_id\":\"+573400000001\",\"email\":\"superseded@test.com\",\"bote_id\":\"bravo_290\",\"lead_id\":\"$LB\",\"plan_id\":\"atardecer_bahia\",\"num_pax\":10,\"fecha_salida\":\"2026-04-15\",\"idioma\":\"es\",\"hora_salida_real\":\"17:00:00\",\"horas_extra\":0}"; sleep 5
cot "{\"whatsapp_id\":\"+573400000001\",\"email\":\"superseded@test.com\",\"bote_id\":\"bravo_380\",\"lead_id\":\"$LB\",\"plan_id\":\"atardecer_bahia\",\"num_pax\":10,\"fecha_salida\":\"2026-04-15\",\"idioma\":\"es\",\"hora_salida_real\":\"17:00:00\",\"horas_extra\":0}"; sleep 5
cot "{\"whatsapp_id\":\"+573400000001\",\"email\":\"superseded@test.com\",\"bote_id\":\"bravo_410\",\"lead_id\":\"$LB\",\"plan_id\":\"atardecer_bahia\",\"num_pax\":10,\"fecha_salida\":\"2026-04-15\",\"idioma\":\"es\",\"hora_salida_real\":\"17:00:00\",\"horas_extra\":0}"; sleep 5
cot "{\"whatsapp_id\":\"+573400000001\",\"email\":\"superseded@test.com\",\"bote_id\":\"firpol_42\",\"lead_id\":\"$LB\",\"plan_id\":\"atardecer_bahia\",\"num_pax\":10,\"fecha_salida\":\"2026-04-15\",\"idioma\":\"es\",\"hora_salida_real\":\"17:00:00\",\"horas_extra\":0}"; sleep 5
cot "{\"whatsapp_id\":\"+573400000001\",\"email\":\"superseded@test.com\",\"bote_id\":\"todomar_44\",\"lead_id\":\"$LB\",\"plan_id\":\"atardecer_bahia\",\"num_pax\":10,\"fecha_salida\":\"2026-04-15\",\"idioma\":\"es\",\"hora_salida_real\":\"17:00:00\",\"horas_extra\":0}"; sleep 5

echo ""
echo "=== TODO DONE ==="
