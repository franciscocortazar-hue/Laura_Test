#!/bin/bash
WL="https://hook.us2.make.com/svepg2mtc1qwqe3fw5l9jvm26amdsxvx"
WC="https://hook.us2.make.com/qx52sszmy6g57a3mt2v524ttdefqm64t"
PASS=0; FAIL=0

reg() { curl -s -X POST "$WL" -H "Content-Type: application/json" -d "{\"whatsapp_id\":\"$1\",\"email\":\"$2\",\"nombre_full\":\"$3\",\"plan_id\":\"atardecer_bahia\",\"num_pax\":$4,\"fecha_salida\":\"$5\",\"idioma\":\"${6:-es}\",\"hora_salida_real\":\"17:00:00\",\"source\":\"landing\"}"; }
cot() { curl -s -X POST "$WC" -H "Content-Type: application/json" -d "{\"whatsapp_id\":\"$1\",\"email\":\"$2\",\"bote_id\":\"$3\",\"lead_id\":\"\",\"plan_id\":\"atardecer_bahia\",\"num_pax\":$4,\"fecha_salida\":\"$5\",\"idioma\":\"${6:-es}\",\"hora_salida_real\":\"17:00:00\",\"horas_extra\":0}"; }

check() {
  local LABEL=$1 R=$2 EXP_BOTE=$3 EXP_VIG=$4 EXP_TEMP=$5
  local OK=$(echo "$R" | grep -o '"ok":true')
  local BOTE=$(echo "$R" | grep -o '"bote_id":"[^"]*"' | cut -d'"' -f4)
  local VIG=$(echo "$R" | grep -o '"vigencia_hasta":"[^"]*"' | cut -d'"' -f4)
  local TEMP=$(echo "$R" | grep -o '"temporada_aplicada":"[^"]*"' | cut -d'"' -f4)
  local NUM=$(echo "$R" | grep -o '"numero_cotizacion":"[^"]*"' | cut -d'"' -f4)
  local PASS_LOCAL=true
  [ -z "$OK" ] && PASS_LOCAL=false
  [ -n "$EXP_BOTE" ] && [ "$BOTE" != "$EXP_BOTE" ] && PASS_LOCAL=false
  [ -n "$EXP_VIG" ] && [ "$VIG" != "$EXP_VIG" ] && PASS_LOCAL=false
  [ -n "$EXP_TEMP" ] && [ "$TEMP" != "$EXP_TEMP" ] && PASS_LOCAL=false
  if [ "$PASS_LOCAL" = "true" ]; then
    echo "  ✅ PASS | $LABEL | bote=$BOTE | vig=$VIG | temp=$TEMP | $NUM"
    ((PASS++))
  else
    echo "  ❌ FAIL | $LABEL"
    echo "         bote: esp=$EXP_BOTE real=$BOTE"
    echo "         vig:  esp=$EXP_VIG  real=$VIG"
    echo "         temp: esp=$EXP_TEMP real=$TEMP"
    ((FAIL++))
  fi
}

echo "======================================"
echo "  B4U — VERIFY FIX bote_id+vigencia"
echo "======================================"

echo ""
echo "--- Test 1: baja/bravo_290 | vig=2026-04-15 ---"
R=$(reg "+573700000001" "t1@test.com" "Test 1" 2 "2026-04-15"); sleep 3
R=$(cot "+573700000001" "t1@test.com" "bravo_290" 2 "2026-04-15"); sleep 5
check "T1/bravo_290/baja" "$R" "bravo_290" "2026-04-15" "baja"

echo ""
echo "--- Test 2: primera cot bote_id no es null ---"
R=$(reg "+573700000002" "t2@test.com" "Test 2" 4 "2026-04-20"); sleep 3
R=$(cot "+573700000002" "t2@test.com" "firpol_34" 4 "2026-04-20"); sleep 5
check "T2/firpol_34/primera-cot" "$R" "firpol_34" "2026-04-20" "baja"

echo ""
echo "--- Test 3: superseded — bote_id correcto en cot2 ---"
R=$(reg "+573700000003" "t3@test.com" "Test 3" 6 "2026-05-10"); sleep 3
R=$(cot "+573700000003" "t3@test.com" "bravo_290" 6 "2026-05-10"); sleep 5
check "T3/C1/bravo_290" "$R" "bravo_290" "2026-05-10" "baja"
R=$(cot "+573700000003" "t3@test.com" "bravo_410" 6 "2026-05-10"); sleep 5
check "T3/C2/bravo_410-sup" "$R" "bravo_410" "2026-05-10" "baja"

echo ""
echo "--- Test 4: superseded 3x — bote_id correcto en cada una ---"
R=$(reg "+573700000004" "t4@test.com" "Test 4" 8 "2026-05-15"); sleep 3
R=$(cot "+573700000004" "t4@test.com" "bravo_290" 8 "2026-05-15"); sleep 5
check "T4/C1/bravo_290" "$R" "bravo_290" "2026-05-15" "baja"
R=$(cot "+573700000004" "t4@test.com" "firpol_42" 8 "2026-05-15"); sleep 5
check "T4/C2/firpol_42" "$R" "firpol_42" "2026-05-15" "baja"
R=$(cot "+573700000004" "t4@test.com" "todomar_44" 8 "2026-05-15"); sleep 5
check "T4/C3/todomar_44" "$R" "todomar_44" "2026-05-15" "baja"

echo ""
echo "--- Test 5: alta/bravo_410/vig=2026-06-20 ---"
R=$(reg "+573700000005" "t5@test.com" "Test 5" 4 "2026-06-20"); sleep 3
R=$(cot "+573700000005" "t5@test.com" "bravo_410" 4 "2026-06-20"); sleep 5
check "T5/bravo_410/alta" "$R" "bravo_410" "2026-06-20" "alta"

echo ""
echo "--- Test 6: EN/bravo_290/alta/vig=2026-07-15 ---"
R=$(reg "+573700000006" "t6@test.com" "Test 6 EN" 3 "2026-07-15" "en"); sleep 3
R=$(cot "+573700000006" "t6@test.com" "bravo_290" 3 "2026-07-15" "en"); sleep 5
check "T6/EN/bravo_290/alta" "$R" "bravo_290" "2026-07-15" "alta"

echo ""
echo "======================================"
echo "  TOTAL: $((PASS+FAIL)) | ✅ $PASS | ❌ $FAIL"
[ $FAIL -eq 0 ] && echo "  🎉 FIX VERIFICADO — Fase 2 CERRADA" || echo "  ⚠️  Revisar logs de Make"
echo "======================================"
