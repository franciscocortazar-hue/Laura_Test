#!/bin/bash
WL="https://hook.us2.make.com/svepg2mtc1qwqe3fw5l9jvm26amdsxvx"
WC="https://hook.us2.make.com/qx52sszmy6g57a3mt2v524ttdefqm64t"
PASS=0; FAIL=0; TOTAL=0

reg() {
  local IDIOMA=${6:-es}; local SOURCE=${7:-landing}
  curl -s -X POST "$WL" -H "Content-Type: application/json" \
    -d "{\"whatsapp_id\":\"$1\",\"email\":\"$2\",\"nombre_full\":\"$3\",\"plan_id\":\"atardecer_bahia\",\"num_pax\":$4,\"fecha_salida\":\"$5\",\"idioma\":\"$IDIOMA\",\"hora_salida_real\":\"17:00:00\",\"source\":\"$SOURCE\"}"
}

cot() {
  local IDIOMA=${6:-es}; local EXTRA=${7:-0}
  curl -s -X POST "$WC" -H "Content-Type: application/json" \
    -d "{\"whatsapp_id\":\"$1\",\"email\":\"$2\",\"bote_id\":\"$3\",\"lead_id\":\"\",\"plan_id\":\"atardecer_bahia\",\"num_pax\":$5,\"fecha_salida\":\"$4\",\"idioma\":\"$IDIOMA\",\"hora_salida_real\":\"17:00:00\",\"horas_extra\":$EXTRA}"
}

check() {
  ((TOTAL++))
  local OK=$(echo "$2" | grep -o '"ok":true')
  local NUM=$(echo "$2" | grep -o '"numero_cotizacion":"[^"]*"' | cut -d'"' -f4)
  local TEMP=$(echo "$2" | grep -o '"temporada_aplicada":"[^"]*"' | cut -d'"' -f4)
  local COP=$(echo "$2" | grep -o '"total_cotizado_cop":[0-9]*' | cut -d':' -f2)
  if [ -n "$OK" ]; then
    if [ -n "$3" ] && [ "$TEMP" != "$3" ]; then
      echo "  ❌ FAIL | $1 | temp esp=$3 real=$TEMP | $NUM"; ((FAIL++))
    else
      echo "  ✅ PASS | $1 | $NUM | ${COP} COP | $TEMP"; ((PASS++))
    fi
  else
    echo "  ❌ FAIL | $1 | $(echo $2 | head -c 120)"; ((FAIL++))
  fi
}

check_reg() {
  ((TOTAL++))
  local LID=$(echo "$2" | grep -o '"lead_id":"[^"]*"' | cut -d'"' -f4)
  [ -n "$LID" ] && echo "  ✅ PASS | $1" && ((PASS++)) || echo "  ❌ FAIL | $1 | $(echo $2 | head -c 80)" && ((FAIL++))
}

sep() { echo ""; echo "============================================================"; echo "  $1"; echo "============================================================"; }
sec() { echo ""; echo "--- $1 ---"; }

FBAJA1="2026-04-15"; FBAJA2="2026-04-20"; FBAJA3="2026-05-10"
FALTA1="2026-06-20"; FALTA2="2026-07-15"

sep "B4U STRESS TEST v2 — $(date '+%Y-%m-%d %H:%M:%S')"
echo "Duracion estimada: ~25 minutos. BD debe estar limpia."

sep "BLOQUE 1 — REGISTRO (8 casos)"

sec "1.1 Clientes nuevos"
for i in 1 2 3 4 5; do
  R=$(reg "+57360000000$i" "stress$i@test.com" "Stress $i" $((i+1)) $FBAJA1)
  sleep 2; check_reg "Reg-cliente-$i (pax=$((i+1)))" "$R"
done

sec "1.2 Ruta 1 WID-existe+email-nuevo"
R=$(reg "+573600000001" "diferente@gmail.com" "Stress 1 Alt" 3 $FBAJA2)
sleep 2; check_reg "Reg-Ruta1" "$R"

sec "1.3 Idioma EN"
R=$(reg "+573600000010" "john@test.com" "John Smith" 2 $FBAJA1 "en")
sleep 2; check_reg "Reg-idioma-EN" "$R"

sec "1.4 Source whatsapp"
R=$(reg "+573600000011" "wa@test.com" "WA Direct" 2 $FBAJA1 "es" "whatsapp")
sleep 2; check_reg "Reg-source-whatsapp" "$R"

sep "BLOQUE 2 — COTIZACIONES SIMPLES (14 casos)"

sec "2.1 Baja todos los botes"
IDX=20
for BOTE in bravo_290 bravo_300 firpol_34 bravo_380 bravo_410 firpol_42 todomar_44; do
  WID="+5736001$IDX"; MAIL="baja$IDX@test.com"
  R=$(reg "$WID" "$MAIL" "Baja $IDX" 4 $FBAJA1); sleep 2
  R=$(cot "$WID" "$MAIL" "$BOTE" $FBAJA1 4); sleep 4
  check "Baja/$BOTE" "$R" "baja"; ((IDX++))
done

sec "2.2 Alta dos botes"
for BOTE in bravo_290 bravo_410; do
  WID="+5736002$IDX"; MAIL="alta$IDX@test.com"
  R=$(reg "$WID" "$MAIL" "Alta $IDX" 4 $FALTA1); sleep 2
  R=$(cot "$WID" "$MAIL" "$BOTE" $FALTA1 4); sleep 4
  check "Alta/$BOTE" "$R" "alta"; ((IDX++))
done

sec "2.3 Horas extra"
WID="+5736003001"; MAIL="extra01@test.com"
R=$(reg "$WID" "$MAIL" "Extra 2h" 4 $FBAJA1); sleep 2
R=$(cot "$WID" "$MAIL" "bravo_410" $FBAJA1 4 "es" 2); sleep 4; check "2h-extra/bravo_410" "$R" "baja"
WID="+5736003002"; MAIL="extra02@test.com"
R=$(reg "$WID" "$MAIL" "Extra 3h" 6 $FBAJA2); sleep 2
R=$(cot "$WID" "$MAIL" "firpol_42" $FBAJA2 6 "es" 3); sleep 4; check "3h-extra/firpol_42" "$R" "baja"

sec "2.4 Grupos grandes"
WID="+5736003010"; R=$(reg "$WID" "g10@test.com" "Grupo15" 15 $FBAJA2); sleep 2
R=$(cot "$WID" "g10@test.com" "firpol_42" $FBAJA2 15); sleep 4; check "15pax/firpol_42" "$R"
WID="+5736003011"; R=$(reg "$WID" "g11@test.com" "Grupo20" 20 $FBAJA3); sleep 2
R=$(cot "$WID" "g11@test.com" "todomar_44" $FBAJA3 20); sleep 4; check "20pax/todomar_44" "$R"

sec "2.5 EN cotizacion"
WID="+5736003020"; R=$(reg "$WID" "en20@test.com" "John20" 2 $FBAJA1 "en"); sleep 2
R=$(cot "$WID" "en20@test.com" "bravo_290" $FBAJA1 2 "en"); sleep 4; check "EN/bravo_290" "$R"

sep "BLOQUE 3 — SUPERSEDED (34 casos)"

sec "3.1 Cambia 3 veces"
WID="+5736010001"; R=$(reg "$WID" "sup3@test.com" "Sup3" 6 $FBAJA1); sleep 3
for BOTE in bravo_290 bravo_410 firpol_42; do
  R=$(cot "$WID" "sup3@test.com" "$BOTE" $FBAJA1 6); sleep 5; check "3x/$BOTE" "$R"
done

sec "3.2 Cambia 5 veces"
WID="+5736010002"; R=$(reg "$WID" "sup5@test.com" "Sup5" 8 $FBAJA2); sleep 3
for BOTE in bravo_290 bravo_300 bravo_380 bravo_410 todomar_44; do
  R=$(cot "$WID" "sup5@test.com" "$BOTE" $FBAJA2 8); sleep 5; check "5x/$BOTE" "$R"
done

sec "3.3 Cambia 8 veces (stress)"
WID="+5736010003"; R=$(reg "$WID" "sup8@test.com" "Sup8" 10 $FBAJA3); sleep 3
for BOTE in bravo_290 bravo_300 firpol_34 bravo_380 bravo_410 firpol_42 todomar_44 bravo_290; do
  R=$(cot "$WID" "sup8@test.com" "$BOTE" $FBAJA3 10); sleep 5; check "8x/$BOTE" "$R"
done

sec "3.4 Superseded en ALTA"
WID="+5736010004"; R=$(reg "$WID" "supalta@test.com" "SupAlta" 4 $FALTA1); sleep 3
for BOTE in bravo_290 bravo_410 firpol_42; do
  R=$(cot "$WID" "supalta@test.com" "$BOTE" $FALTA1 4); sleep 5; check "Alta-sup/$BOTE" "$R" "alta"
done

sec "3.5 Dos clientes en paralelo 3x cada uno"
WID_A="+5736010010"; WID_B="+5736010011"
R=$(reg "$WID_A" "parA@test.com" "ParA" 4 $FBAJA1); sleep 2
R=$(reg "$WID_B" "parB@test.com" "ParB" 5 $FBAJA1); sleep 2
BOTES_A=(bravo_290 firpol_34 bravo_380)
BOTES_B=(bravo_410 todomar_44 bravo_300)
for i in 0 1 2; do
  R=$(cot "$WID_A" "parA@test.com" "${BOTES_A[$i]}" $FBAJA1 4); sleep 3; check "ParA-$((i+1))/${BOTES_A[$i]}" "$R"
  R=$(cot "$WID_B" "parB@test.com" "${BOTES_B[$i]}" $FBAJA1 5); sleep 3; check "ParB-$((i+1))/${BOTES_B[$i]}" "$R"
done

sec "3.6 Secuencia 10 cotizaciones — numeracion"
WID="+5736010020"; R=$(reg "$WID" "seq10@test.com" "Seq10" 4 $FBAJA3); sleep 3
BOTES10=(bravo_290 bravo_300 firpol_34 bravo_380 bravo_410 firpol_42 todomar_44 bravo_290 bravo_300 firpol_34)
for i in 0 1 2 3 4 5 6 7 8 9; do
  R=$(cot "$WID" "seq10@test.com" "${BOTES10[$i]}" $FBAJA3 4); sleep 5
  NUM=$(echo "$R" | grep -o '"numero_cotizacion":"[^"]*"' | cut -d'"' -f4)
  SUFFIX=$(printf "%02d" $((i+1)))
  ((TOTAL++))
  [[ "$NUM" == *"-$SUFFIX" ]] && echo "  ✅ PASS | Cot$((i+1))/10: $NUM" && ((PASS++)) || echo "  ❌ FAIL | Cot$((i+1))/10: esp=*-$SUFFIX got='$NUM'" && ((FAIL++))
done

sep "BLOQUE 4 — MULTIPLES LEADS (9 casos)"

sec "4.1 3 leads distintos — WIDs unicos por lead"
FECHAS_ML=($FBAJA1 $FBAJA2 $FALTA1)
BOTES_ML=(bravo_290 bravo_410 firpol_42)
TEMPS_ML=(baja baja alta)
for i in 1 2 3; do
  WID="+573602000$i"; MAIL="ml$i@test.com"
  R=$(reg "$WID" "$MAIL" "ML$i" $((i+2)) "${FECHAS_ML[$((i-1))]}"); sleep 2
  R=$(cot "$WID" "$MAIL" "${BOTES_ML[$((i-1))]}" "${FECHAS_ML[$((i-1))]}" $((i+2))); sleep 4
  check "ML-lead$i/${BOTES_ML[$((i-1))]}" "$R" "${TEMPS_ML[$((i-1))]}"
done

sec "4.2 Lead con 3 sup + nuevo lead independiente"
WID1="+5736020010"; WID2="+5736020011"; MAIL="indep@test.com"
R=$(reg "$WID1" "$MAIL" "Indep L1" 4 $FBAJA1); sleep 2
R=$(cot "$WID1" "$MAIL" "bravo_290" $FBAJA1 4); sleep 4; check "Indep/L1-C1" "$R"
R=$(cot "$WID1" "$MAIL" "bravo_410" $FBAJA1 4); sleep 4; check "Indep/L1-C2-sup" "$R"
R=$(cot "$WID1" "$MAIL" "firpol_42" $FBAJA1 4); sleep 4; check "Indep/L1-C3-sup" "$R"
R=$(reg "$WID2" "$MAIL" "Indep L2" 4 $FALTA2); sleep 2
R=$(cot "$WID2" "$MAIL" "todomar_44" $FALTA2 4); sleep 4; check "Indep/L2-C1-alta" "$R" "alta"

sec "4.3 EN con sup + lead adicional"
WID1="+5736020020"; WID2="+5736020021"; MAIL="en_ml@test.com"
R=$(reg "$WID1" "$MAIL" "EN Multi" 2 $FBAJA1 "en"); sleep 2
R=$(cot "$WID1" "$MAIL" "bravo_290" $FBAJA1 2 "en"); sleep 4; check "EN/L1-C1" "$R"
R=$(cot "$WID1" "$MAIL" "bravo_410" $FBAJA1 2 "en"); sleep 4; check "EN/L1-C2-sup" "$R"
R=$(reg "$WID2" "$MAIL" "EN Multi L2" 4 $FALTA1 "en"); sleep 2
R=$(cot "$WID2" "$MAIL" "firpol_42" $FALTA1 4 "en"); sleep 4; check "EN/L2-C1-alta" "$R" "alta"

sep "BLOQUE 5 — FECHAS BORDE (12 casos)"

sec "5.1 Semana Santa"
for ITEM in "+5736030001:2026-03-28:baja:Antes-SS" "+5736030002:2026-03-29:alta:Inicio-SS" "+5736030003:2026-04-05:alta:Fin-SS" "+5736030004:2026-04-06:baja:Despues-SS"; do
  WID=$(echo $ITEM|cut -d: -f1); FECHA=$(echo $ITEM|cut -d: -f2); TEMP=$(echo $ITEM|cut -d: -f3); LABEL=$(echo $ITEM|cut -d: -f4)
  R=$(reg "$WID" "${WID:1}@t.com" "Borde $LABEL" 2 "$FECHA"); sleep 2
  R=$(cot "$WID" "${WID:1}@t.com" "bravo_290" "$FECHA" 2); sleep 4
  check "SS/$LABEL" "$R" "$TEMP"
done

sec "5.2 Mitad de Año"
for ITEM in "+5736030010:2026-06-14:baja:Antes-MY" "+5736030011:2026-06-15:alta:Inicio-MY" "+5736030012:2026-07-31:alta:Fin-MY" "+5736030013:2026-08-01:baja:Despues-MY"; do
  WID=$(echo $ITEM|cut -d: -f1); FECHA=$(echo $ITEM|cut -d: -f2); TEMP=$(echo $ITEM|cut -d: -f3); LABEL=$(echo $ITEM|cut -d: -f4)
  R=$(reg "$WID" "${WID:1}@t.com" "Borde $LABEL" 2 "$FECHA"); sleep 2
  R=$(cot "$WID" "${WID:1}@t.com" "bravo_290" "$FECHA" 2); sleep 4
  check "MY/$LABEL" "$R" "$TEMP"
done

sec "5.3 Dic-Ene"
for ITEM in "+5736030020:2025-12-14:baja:Antes-DE" "+5736030021:2025-12-15:alta:Inicio-DE" "+5736030022:2026-01-15:alta:Fin-DE" "+5736030023:2026-01-16:baja:Despues-DE"; do
  WID=$(echo $ITEM|cut -d: -f1); FECHA=$(echo $ITEM|cut -d: -f2); TEMP=$(echo $ITEM|cut -d: -f3); LABEL=$(echo $ITEM|cut -d: -f4)
  R=$(reg "$WID" "${WID:1}@t.com" "Borde $LABEL" 2 "$FECHA"); sleep 2
  R=$(cot "$WID" "${WID:1}@t.com" "bravo_290" "$FECHA" 2); sleep 4
  check "DE/$LABEL" "$R" "$TEMP"
done

sep "RESUMEN FINAL"
echo ""
echo "  Total : $TOTAL"
echo "  ✅ PASS: $PASS"
echo "  ❌ FAIL: $FAIL"
[ $TOTAL -gt 0 ] && echo "  📊 Score: $(( PASS * 100 / TOTAL ))%"
[ $FAIL -eq 0 ] && [ $TOTAL -gt 0 ] && echo "" && echo "  🎉 CRM FASE 2 — TODOS LOS ESCENARIOS PASARON"
echo ""
echo "  Fin: $(date '+%Y-%m-%d %H:%M:%S')"
