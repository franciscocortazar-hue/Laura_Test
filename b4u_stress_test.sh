#!/bin/bash
# ============================================================
# B4U CRM FASE 2 — STRESS TEST SUITE COMPLETO
# LEO — CTO Proyecto Caribe Digital | Abril 2026
# ~100 casos cubriendo todas las máquinas de estado
# ============================================================

WL="https://hook.us2.make.com/svepg2mtc1qwqe3fw5l9jvm26amdsxvx"
WC="https://hook.us2.make.com/qx52sszmy6g57a3mt2v524ttdefqm64t"
PASS=0; FAIL=0

reg() {
  local WID=$1 MAIL=$2 NOMBRE=$3 PAX=$4 FECHA=$5 IDIOMA=${6:-es} SOURCE=${7:-landing}
  curl -s -X POST "$WL" -H "Content-Type: application/json" \
    -d "{\"whatsapp_id\":\"$WID\",\"email\":\"$MAIL\",\"nombre_full\":\"$NOMBRE\",\"plan_id\":\"atardecer_bahia\",\"num_pax\":$PAX,\"fecha_salida\":\"$FECHA\",\"idioma\":\"$IDIOMA\",\"hora_salida_real\":\"17:00:00\",\"source\":\"$SOURCE\"}" \
    | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('lead_id',''))" 2>/dev/null
}

cot() {
  local WID=$1 MAIL=$2 BOTE=$3 LID=$4 PAX=$5 FECHA=$6 IDIOMA=${7:-es} EXTRA=${8:-0}
  curl -s -X POST "$WC" -H "Content-Type: application/json" \
    -d "{\"whatsapp_id\":\"$WID\",\"email\":\"$MAIL\",\"bote_id\":\"$BOTE\",\"lead_id\":\"$LID\",\"plan_id\":\"atardecer_bahia\",\"num_pax\":$PAX,\"fecha_salida\":\"$FECHA\",\"idioma\":\"$IDIOMA\",\"hora_salida_real\":\"17:00:00\",\"horas_extra\":$EXTRA}"
}

check() {
  local LABEL=$1 RESULT=$2 EXPECT_OK=${3:-true}
  local OK=$(echo "$RESULT" | python3 -c "import sys,json; d=json.load(sys.stdin); print('true' if d.get('ok')==True else 'false')" 2>/dev/null)
  local NUM=$(echo "$RESULT" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('numero_cotizacion',''))" 2>/dev/null)
  local TEMP=$(echo "$RESULT" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('temporada_aplicada',''))" 2>/dev/null)
  local TOTAL=$(echo "$RESULT" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('total_cotizado_cop',''))" 2>/dev/null)
  if [ "$OK" = "true" ]; then
    echo "  ✅ PASS | $LABEL | $NUM | ${TOTAL} COP | temp=$TEMP"
    ((PASS++))
  else
    echo "  ❌ FAIL | $LABEL | $RESULT" | head -c 200
    echo ""
    ((FAIL++))
  fi
}

sep() { echo ""; echo "============================================================"; echo "  $1"; echo "============================================================"; }
sec() { echo ""; echo "--- $1 ---"; }

# Fechas de prueba
FBAJA1="2026-04-15"; FBAJA2="2026-04-20"; FBAJA3="2026-05-10"
FALTA1="2026-06-20"; FALTA2="2026-07-15"

sep "B4U STRESS TEST — $(date '+%Y-%m-%d %H:%M:%S')"
echo "IMPORTANTE: BD debe estar limpia antes de correr este script"
echo ""

# ============================================================
sep "BLOQUE 1 — REGISTRO DE CLIENTES (10 casos)"
# ============================================================

sec "1.1 Nuevos clientes variantes"
declare -A LEADS
for i in 1 2 3 4 5; do
  N="+57350000000$i"; MAIL="stress$i@test.com"; PAX=$((i+1))
  LID=$(reg "$N" "$MAIL" "Stress $i" $PAX $FBAJA1); sleep 2
  [ -n "$LID" ] && echo "  ✅ PASS | Cliente $i lead_id=[OK]" && ((PASS++)) || echo "  ❌ FAIL | Cliente $i lead_id=[VACIO]" && ((FAIL++))
  LEADS[$i]=$LID
done

sec "1.2 Ruta 1 — WID existente + email diferente"
LID_R1=$(reg "+573500000001" "diferente@gmail.com" "Stress 1" 3 $FBAJA2); sleep 2
[ -n "$LID_R1" ] && echo "  ✅ PASS | Ruta 1 OK" && ((PASS++)) || echo "  ❌ FAIL | Ruta 1" && ((FAIL++))

sec "1.3 Ruta 3 — WID nuevo + email existente"
LID_R3=$(reg "+573500009999" "stress1@test.com" "Alt WID" 2 $FBAJA3); sleep 2
[ -n "$LID_R3" ] && echo "  ✅ PASS | Ruta 3 OK" && ((PASS++)) || echo "  ❌ FAIL | Ruta 3" && ((FAIL++))

sec "1.4 Idioma EN"
LID_EN=$(reg "+573500000010" "john@test.com" "John Smith" 2 $FBAJA1 "en"); sleep 2
[ -n "$LID_EN" ] && echo "  ✅ PASS | EN lead OK" && ((PASS++)) || echo "  ❌ FAIL | EN lead" && ((FAIL++))

# ============================================================
sep "BLOQUE 2 — COTIZACIONES SIMPLES (14 casos)"
# ============================================================

sec "2.1 Temporada BAJA — todos los botes"
declare -A PRECIOS_BAJA
PRECIOS_BAJA[bravo_290]=1400000; PRECIOS_BAJA[bravo_300]=1600000
PRECIOS_BAJA[firpol_34]=1800000; PRECIOS_BAJA[bravo_380]=2100000
PRECIOS_BAJA[bravo_410]=2300000; PRECIOS_BAJA[firpol_42]=2300000
PRECIOS_BAJA[todomar_44]=3500000

IDX=11
for BOTE in bravo_290 bravo_300 firpol_34 bravo_380 bravo_410 firpol_42 todomar_44; do
  WID="+5735000$IDX"; MAIL="bote$IDX@test.com"
  LID=$(reg "$WID" "$MAIL" "Baja $IDX" 4 $FBAJA1); sleep 2
  if [ -n "$LID" ]; then
    R=$(cot "$WID" "$MAIL" "$BOTE" "$LID" 4 $FBAJA1); sleep 4
    check "Baja/$BOTE" "$R"
  fi
  ((IDX++))
done

sec "2.2 Temporada ALTA — bravo_290 y bravo_410"
for BOTE in bravo_290 bravo_410; do
  WID="+5735000$IDX"; MAIL="alta$IDX@test.com"
  LID=$(reg "$WID" "$MAIL" "Alta $IDX" 4 $FALTA1); sleep 2
  if [ -n "$LID" ]; then
    R=$(cot "$WID" "$MAIL" "$BOTE" "$LID" 4 $FALTA1); sleep 4
    check "Alta/$BOTE" "$R"
  fi
  ((IDX++))
done

sec "2.3 Con horas extra"
WID="+5735000100"; MAIL="extra100@test.com"
LID=$(reg "$WID" "$MAIL" "Extra 100" 4 $FBAJA1); sleep 2
if [ -n "$LID" ]; then
  R=$(cot "$WID" "$MAIL" "bravo_410" "$LID" 4 $FBAJA1 "es" 2); sleep 4
  check "2h extra/bravo_410" "$R"
fi

sec "2.4 Grupo grande 15 pax"
WID="+5735000101"; MAIL="grupo101@test.com"
LID=$(reg "$WID" "$MAIL" "Grupo 101" 15 $FBAJA2); sleep 2
if [ -n "$LID" ]; then
  R=$(cot "$WID" "$MAIL" "firpol_42" "$LID" 15 $FBAJA2); sleep 4
  check "15pax/firpol_42" "$R"
fi

sec "2.5 Idioma EN cotización"
if [ -n "$LID_EN" ]; then
  R=$(cot "+573500000010" "john@test.com" "bravo_290" "$LID_EN" 2 $FBAJA1 "en"); sleep 4
  check "EN/bravo_290" "$R"
fi

# ============================================================
sep "BLOQUE 3 — SUPERSEDED 3x, 5x, 8x (30 casos)"
# ============================================================

sec "3.1 Cliente cambia bote 3 veces"
WID="+5735001000"; MAIL="sup3@test.com"
LID=$(reg "$WID" "$MAIL" "Sup3" 6 $FBAJA1); sleep 3
if [ -n "$LID" ]; then
  for BOTE in bravo_290 bravo_410 firpol_42; do
    R=$(cot "$WID" "$MAIL" "$BOTE" "$LID" 6 $FBAJA1); sleep 5
    check "3x-sup/$BOTE" "$R"
  done
fi

sec "3.2 Cliente cambia bote 5 veces"
WID="+5735001001"; MAIL="sup5@test.com"
LID=$(reg "$WID" "$MAIL" "Sup5" 8 $FBAJA2); sleep 3
if [ -n "$LID" ]; then
  for BOTE in bravo_290 bravo_300 bravo_380 bravo_410 todomar_44; do
    R=$(cot "$WID" "$MAIL" "$BOTE" "$LID" 8 $FBAJA2); sleep 5
    check "5x-sup/$BOTE" "$R"
  done
fi

sec "3.3 Cliente cambia bote 8 veces (stress)"
WID="+5735001002"; MAIL="sup8@test.com"
LID=$(reg "$WID" "$MAIL" "Sup8" 10 $FBAJA3); sleep 3
if [ -n "$LID" ]; then
  for BOTE in bravo_290 bravo_300 firpol_34 bravo_380 bravo_410 firpol_42 todomar_44 bravo_290; do
    R=$(cot "$WID" "$MAIL" "$BOTE" "$LID" 10 $FBAJA3); sleep 5
    check "8x-sup/$BOTE" "$R"
  done
fi

sec "3.4 Superseded en temporada ALTA"
WID="+5735001003"; MAIL="supalta@test.com"
LID=$(reg "$WID" "$MAIL" "SupAlta" 4 $FALTA1); sleep 3
if [ -n "$LID" ]; then
  for BOTE in bravo_290 bravo_410 firpol_42; do
    R=$(cot "$WID" "$MAIL" "$BOTE" "$LID" 4 $FALTA1); sleep 5
    check "Alta-sup/$BOTE" "$R"
  done
fi

sec "3.5 Dos clientes cambian botes en paralelo (secuencial)"
WID_A="+5735001010"; WID_B="+5735001011"
MAIL_A="parA@test.com"; MAIL_B="parB@test.com"
LID_A=$(reg "$WID_A" "$MAIL_A" "ParA" 4 $FBAJA1); sleep 2
LID_B=$(reg "$WID_B" "$MAIL_B" "ParB" 5 $FBAJA1); sleep 2
if [ -n "$LID_A" ] && [ -n "$LID_B" ]; then
  BOTES_A=(bravo_290 firpol_34 bravo_380)
  BOTES_B=(bravo_410 todomar_44 bravo_300)
  for i in 0 1 2; do
    R_A=$(cot "$WID_A" "$MAIL_A" "${BOTES_A[$i]}" "$LID_A" 4 $FBAJA1); sleep 3
    R_B=$(cot "$WID_B" "$MAIL_B" "${BOTES_B[$i]}" "$LID_B" 5 $FBAJA1); sleep 3
    check "ParA-$((i+1))/${BOTES_A[$i]}" "$R_A"
    check "ParB-$((i+1))/${BOTES_B[$i]}" "$R_B"
  done
fi

sec "3.6 Secuencia 10 cotizaciones — verificar numeración"
WID="+5735001020"; MAIL="seq10@test.com"
LID=$(reg "$WID" "$MAIL" "Seq10" 4 $FBAJA3); sleep 3
if [ -n "$LID" ]; then
  BOTES=(bravo_290 bravo_300 firpol_34 bravo_380 bravo_410 firpol_42 todomar_44 bravo_290 bravo_300 firpol_34)
  for i in 0 1 2 3 4 5 6 7 8 9; do
    R=$(cot "$WID" "$MAIL" "${BOTES[$i]}" "$LID" 4 $FBAJA3); sleep 5
    NUM=$(echo "$R" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('numero_cotizacion',''))" 2>/dev/null)
    SUFFIX=$(printf "%02d" $((i+1)))
    [[ "$NUM" == *"-$SUFFIX" ]] && echo "  ✅ PASS | Cot$((i+1))/10: $NUM" && ((PASS++)) || echo "  ❌ FAIL | Cot$((i+1))/10: esperado -*-$SUFFIX, got $NUM" && ((FAIL++))
  done
fi

# ============================================================
sep "BLOQUE 4 — MÚLTIPLES LEADS POR CLIENTE (12 casos)"
# ============================================================

sec "4.1 Cliente con 3 leads en fechas distintas"
WID="+5735002000"; MAIL="multilead@test.com"
LID_A=$(reg "$WID" "$MAIL" "MultiLead" 2 $FBAJA1); sleep 2
LID_B=$(reg "$WID" "$MAIL" "MultiLead" 3 $FBAJA2); sleep 2
LID_C=$(reg "$WID" "$MAIL" "MultiLead" 4 $FALTA1); sleep 2
[ -n "$LID_A" ] && echo "  ✅ PASS | Lead A creado" && ((PASS++)) || echo "  ❌ FAIL | Lead A" && ((FAIL++))
[ -n "$LID_B" ] && echo "  ✅ PASS | Lead B creado" && ((PASS++)) || echo "  ❌ FAIL | Lead B" && ((FAIL++))
[ -n "$LID_C" ] && echo "  ✅ PASS | Lead C creado" && ((PASS++)) || echo "  ❌ FAIL | Lead C" && ((FAIL++))
if [ -n "$LID_A" ]; then
  R=$(cot "$WID" "$MAIL" "bravo_290" "$LID_A" 2 $FBAJA1); sleep 4; check "ML/Lead-A" "$R"
fi
if [ -n "$LID_B" ]; then
  R=$(cot "$WID" "$MAIL" "bravo_410" "$LID_B" 3 $FBAJA2); sleep 4; check "ML/Lead-B" "$R"
fi
if [ -n "$LID_C" ]; then
  R=$(cot "$WID" "$MAIL" "firpol_42" "$LID_C" 4 $FALTA1); sleep 4; check "ML/Lead-C-alta" "$R"
fi

sec "4.2 Lead A cotiza 2 veces, Lead B 1 vez — mismo cliente"
WID="+5735002001"; MAIL="dual@test.com"
LID1=$(reg "$WID" "$MAIL" "Dual" 3 $FBAJA1); sleep 2
LID2=$(reg "$WID" "$MAIL" "Dual" 5 $FBAJA2); sleep 2
if [ -n "$LID1" ] && [ -n "$LID2" ]; then
  R=$(cot "$WID" "$MAIL" "bravo_290" "$LID1" 3 $FBAJA1); sleep 4; check "Dual/L1-C1" "$R"
  R=$(cot "$WID" "$MAIL" "bravo_410" "$LID1" 3 $FBAJA1); sleep 4; check "Dual/L1-C2-sup" "$R"
  R=$(cot "$WID" "$MAIL" "firpol_34" "$LID2" 5 $FBAJA2); sleep 4; check "Dual/L2-C1" "$R"
fi

sec "4.3 Lead con superseded + nuevo lead independiente"
WID="+5735002002"; MAIL="indep@test.com"
LID1=$(reg "$WID" "$MAIL" "Indep" 4 $FBAJA1); sleep 2
if [ -n "$LID1" ]; then
  R=$(cot "$WID" "$MAIL" "bravo_290" "$LID1" 4 $FBAJA1); sleep 4; check "Indep/L1-C1" "$R"
  R=$(cot "$WID" "$MAIL" "bravo_410" "$LID1" 4 $FBAJA1); sleep 4; check "Indep/L1-C2-sup" "$R"
  LID2=$(reg "$WID" "$MAIL" "Indep" 4 $FALTA2); sleep 2
  if [ -n "$LID2" ]; then
    R=$(cot "$WID" "$MAIL" "firpol_42" "$LID2" 4 $FALTA2); sleep 4; check "Indep/L2-C1-alta" "$R"
  fi
fi

# ============================================================
sep "BLOQUE 5 — FECHAS BORDE TEMPORADAS (12 casos)"
# ============================================================

sec "5.1 Bordes Semana Santa"
FECHAS_SS=(
  "2026-03-28:baja:Antes-SS"
  "2026-03-29:alta:Inicio-SS"
  "2026-04-05:alta:Fin-SS"
  "2026-04-06:baja:Despues-SS"
)
IDX=3000
for ITEM in "${FECHAS_SS[@]}"; do
  FECHA=$(echo $ITEM | cut -d: -f1)
  TEMP_ESP=$(echo $ITEM | cut -d: -f2)
  LABEL=$(echo $ITEM | cut -d: -f3)
  WID="+573500$IDX"; MAIL="borde$IDX@test.com"
  LID=$(reg "$WID" "$MAIL" "Borde $IDX" 2 "$FECHA"); sleep 2
  if [ -n "$LID" ]; then
    R=$(cot "$WID" "$MAIL" "bravo_290" "$LID" 2 "$FECHA"); sleep 4
    TEMP_REAL=$(echo "$R" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('temporada_aplicada','?'))" 2>/dev/null)
    OK=$(echo "$R" | python3 -c "import sys,json; d=json.load(sys.stdin); print('true' if d.get('ok') else 'false')" 2>/dev/null)
    [ "$OK" = "true" ] && [ "$TEMP_REAL" = "$TEMP_ESP" ] && echo "  ✅ PASS | $LABEL($FECHA): temp=$TEMP_REAL" && ((PASS++)) || echo "  ❌ FAIL | $LABEL($FECHA): esp=$TEMP_ESP real=$TEMP_REAL ok=$OK" && ((FAIL++))
  fi
  ((IDX++))
done

sec "5.2 Bordes Mitad de Año"
FECHAS_MY=(
  "2026-06-14:baja:Antes-MY"
  "2026-06-15:alta:Inicio-MY"
  "2026-07-31:alta:Fin-MY"
  "2026-08-01:baja:Despues-MY"
)
for ITEM in "${FECHAS_MY[@]}"; do
  FECHA=$(echo $ITEM | cut -d: -f1)
  TEMP_ESP=$(echo $ITEM | cut -d: -f2)
  LABEL=$(echo $ITEM | cut -d: -f3)
  WID="+573500$IDX"; MAIL="borde$IDX@test.com"
  LID=$(reg "$WID" "$MAIL" "Borde $IDX" 2 "$FECHA"); sleep 2
  if [ -n "$LID" ]; then
    R=$(cot "$WID" "$MAIL" "bravo_290" "$LID" 2 "$FECHA"); sleep 4
    TEMP_REAL=$(echo "$R" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('temporada_aplicada','?'))" 2>/dev/null)
    OK=$(echo "$R" | python3 -c "import sys,json; d=json.load(sys.stdin); print('true' if d.get('ok') else 'false')" 2>/dev/null)
    [ "$OK" = "true" ] && [ "$TEMP_REAL" = "$TEMP_ESP" ] && echo "  ✅ PASS | $LABEL($FECHA): temp=$TEMP_REAL" && ((PASS++)) || echo "  ❌ FAIL | $LABEL($FECHA): esp=$TEMP_ESP real=$TEMP_REAL" && ((FAIL++))
  fi
  ((IDX++))
done

sec "5.3 Bordes Dic-Ene"
FECHAS_DE=(
  "2025-12-14:baja:Antes-DE"
  "2025-12-15:alta:Inicio-DE"
  "2026-01-15:alta:Fin-DE"
  "2026-01-16:baja:Despues-DE"
)
for ITEM in "${FECHAS_DE[@]}"; do
  FECHA=$(echo $ITEM | cut -d: -f1)
  TEMP_ESP=$(echo $ITEM | cut -d: -f2)
  LABEL=$(echo $ITEM | cut -d: -f3)
  WID="+573500$IDX"; MAIL="borde$IDX@test.com"
  LID=$(reg "$WID" "$MAIL" "Borde $IDX" 2 "$FECHA"); sleep 2
  if [ -n "$LID" ]; then
    R=$(cot "$WID" "$MAIL" "bravo_290" "$LID" 2 "$FECHA"); sleep 4
    TEMP_REAL=$(echo "$R" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('temporada_aplicada','?'))" 2>/dev/null)
    OK=$(echo "$R" | python3 -c "import sys,json; d=json.load(sys.stdin); print('true' if d.get('ok') else 'false')" 2>/dev/null)
    [ "$OK" = "true" ] && [ "$TEMP_REAL" = "$TEMP_ESP" ] && echo "  ✅ PASS | $LABEL($FECHA): temp=$TEMP_REAL" && ((PASS++)) || echo "  ❌ FAIL | $LABEL($FECHA): esp=$TEMP_ESP real=$TEMP_REAL" && ((FAIL++))
  fi
  ((IDX++))
done

# ============================================================
sep "RESUMEN FINAL"
# ============================================================
TOTAL=$((PASS+FAIL))
echo ""
echo "  Total pruebas ejecutadas: $TOTAL"
echo "  ✅ PASS: $PASS"
echo "  ❌ FAIL: $FAIL"
echo ""
if [ $FAIL -eq 0 ]; then
  echo "  🎉 TODOS LOS ESCENARIOS PASARON — Make + Supabase ESTABLES"
else
  echo "  ⚠️  $FAIL escenario(s) fallaron — revisar logs de Make"
fi
echo ""
echo "  Timestamp fin: $(date '+%Y-%m-%d %H:%M:%S')"
