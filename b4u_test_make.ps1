# ============================================================
# B4U CRM FASE 2 — TEST SCRIPT MAKE (PowerShell)
# Generado por LEO — CTO Proyecto Caribe Digital
# 24 Marzo 2026
#
# COMO USAR:
#   .\b4u_test_make.ps1
#
# Cada grupo tiene pausa de 3s entre llamadas para no
# saturar los escenarios de Make.
# ============================================================

$WEBHOOK_LEAD = "https://hook.us2.make.com/svepg2mtc1qwqe3fw5l9jvm26amdsxvx"
$WEBHOOK_COT  = "https://hook.us2.make.com/qx52sszmy6g57a3mt2v524ttdefqm64t"

Write-Host ""
Write-Host "============================================================"
Write-Host " B4U CRM - TEST SUITE MAKE"
Write-Host "============================================================"


# ============================================================
# GRUPO 1 — SUPERSEDED
# ============================================================

Write-Host ""
Write-Host "------------------------------------------------------------"
Write-Host " GRUPO 1 - SUPERSEDED (mismo lead, 3 cotizaciones)"
Write-Host "------------------------------------------------------------"

Write-Host ""
Write-Host "[1.1] Registrar lead base para prueba superseded..."
$body = @{
    whatsapp_id     = "+573132488737"
    email           = "francisco.cortazar@boats4u.co"
    nombre_full     = "Francisco Cortazar"
    plan_id         = "atardecer_bahia"
    num_pax         = 2
    fecha_salida    = "2026-04-15"
    idioma          = "es"
    hora_salida_real = "17:00:00"
} | ConvertTo-Json
$resp = Invoke-RestMethod -Uri $WEBHOOK_LEAD -Method POST -ContentType "application/json" -Body $body
Write-Host "Response: $($resp | ConvertTo-Json -Compress)"
$LEAD_ID = $resp.lead_id
Write-Host "Lead ID capturado: $LEAD_ID"
Start-Sleep -Seconds 3

Write-Host ""
Write-Host "[1.2] Cotizacion #1 - bravo_290, baja..."
$body = @{
    whatsapp_id     = "+573132488737"
    email           = "francisco.cortazar@boats4u.co"
    bote_id         = "bravo_290"
    lead_id         = $LEAD_ID
    plan_id         = "atardecer_bahia"
    num_pax         = 2
    fecha_salida    = "2026-04-15"
    idioma          = "es"
    hora_salida_real = "17:00:00"
    horas_extra     = 0
} | ConvertTo-Json
Invoke-RestMethod -Uri $WEBHOOK_COT -Method POST -ContentType "application/json" -Body $body
Write-Host ""
Start-Sleep -Seconds 4

Write-Host ""
Write-Host "[1.3] Cotizacion #2 - mismo lead, simula recotizacion..."
$body = @{
    whatsapp_id     = "+573132488737"
    email           = "francisco.cortazar@boats4u.co"
    bote_id         = "bravo_290"
    lead_id         = $LEAD_ID
    plan_id         = "atardecer_bahia"
    num_pax         = 2
    fecha_salida    = "2026-04-15"
    idioma          = "es"
    hora_salida_real = "17:00:00"
    horas_extra     = 0
} | ConvertTo-Json
Invoke-RestMethod -Uri $WEBHOOK_COT -Method POST -ContentType "application/json" -Body $body
Write-Host ""
Start-Sleep -Seconds 4

Write-Host ""
Write-Host "[1.4] Cotizacion #3 - mismo lead, con hora extra..."
$body = @{
    whatsapp_id     = "+573132488737"
    email           = "francisco.cortazar@boats4u.co"
    bote_id         = "bravo_290"
    lead_id         = $LEAD_ID
    plan_id         = "atardecer_bahia"
    num_pax         = 2
    fecha_salida    = "2026-04-15"
    idioma          = "es"
    hora_salida_real = "17:00:00"
    horas_extra     = 1
} | ConvertTo-Json
Invoke-RestMethod -Uri $WEBHOOK_COT -Method POST -ContentType "application/json" -Body $body
Write-Host ""
Start-Sleep -Seconds 3

Write-Host ""
Write-Host ">>> VERIFICAR EN SUPABASE - Grupo 1:"
Write-Host "SELECT numero_cotizacion, estado_cotizacion, total_cotizado, horas_extra"
Write-Host "FROM cotizaciones"
Write-Host "WHERE lead_id = '$LEAD_ID'"
Write-Host "ORDER BY created_at ASC;"
Write-Host ""
Write-Host "Esperado: 2 filas 'superseded', 1 fila 'sent' (la ultima)"


# ============================================================
# GRUPO 2 — PATCH LEAD + TEMPORADA ALTA
# ============================================================

Write-Host ""
Write-Host "------------------------------------------------------------"
Write-Host " GRUPO 2 - PATCH LEAD + TEMPORADA ALTA (Semana Santa)"
Write-Host "------------------------------------------------------------"

Write-Host ""
Write-Host "[2.1] Registrar lead - cliente nuevo, Semana Santa..."
$body = @{
    whatsapp_id     = "+573999000001"
    email           = "test.alta@boats4u.co"
    nombre_full     = "Test Temporada Alta"
    plan_id         = "atardecer_bahia"
    num_pax         = 2
    fecha_salida    = "2026-04-02"
    idioma          = "es"
    hora_salida_real = "17:00:00"
} | ConvertTo-Json
$resp2 = Invoke-RestMethod -Uri $WEBHOOK_LEAD -Method POST -ContentType "application/json" -Body $body
Write-Host "Response: $($resp2 | ConvertTo-Json -Compress)"
$LEAD_ID2 = $resp2.lead_id
Write-Host "Lead ID: $LEAD_ID2"
Start-Sleep -Seconds 3

Write-Host ""
Write-Host "[2.2] Cotizar - bravo_290, fecha Alta (2026-04-02)..."
$body = @{
    whatsapp_id     = "+573999000001"
    email           = "test.alta@boats4u.co"
    bote_id         = "bravo_290"
    lead_id         = $LEAD_ID2
    plan_id         = "atardecer_bahia"
    num_pax         = 2
    fecha_salida    = "2026-04-02"
    idioma          = "es"
    hora_salida_real = "17:00:00"
    horas_extra     = 0
} | ConvertTo-Json
Invoke-RestMethod -Uri $WEBHOOK_COT -Method POST -ContentType "application/json" -Body $body
Write-Host ""
Start-Sleep -Seconds 3

Write-Host ""
Write-Host ">>> VERIFICAR EN SUPABASE - Grupo 2:"
Write-Host "SELECT l.status_lead, l.bote_id, l.cotizacion_activa_id,"
Write-Host "       c.estado_cotizacion, c.total_cotizado, c.temporada_aplicada"
Write-Host "FROM leads l"
Write-Host "LEFT JOIN cotizaciones c ON c.id = l.cotizacion_activa_id"
Write-Host "WHERE l.whatsapp_id = '+573999000001';"
Write-Host ""
Write-Host "Esperado: status_lead='Cotizacion_Enviada', temporada_aplicada='alta', total=1.800.000"


# ============================================================
# GRUPO 3 — VARIANTES DE CLIENTES
# ============================================================

Write-Host ""
Write-Host "------------------------------------------------------------"
Write-Host " GRUPO 3 - VARIANTES DE CLIENTES"
Write-Host "------------------------------------------------------------"

Write-Host ""
Write-Host "[3.1] Mismo WID, diferente email - debe usar cliente existente..."
$body = @{
    whatsapp_id     = "+573132488737"
    email           = "otro.email@gmail.com"
    nombre_full     = "Francisco Cortazar"
    plan_id         = "atardecer_bahia"
    num_pax         = 4
    fecha_salida    = "2026-04-20"
    idioma          = "es"
    hora_salida_real = "17:00:00"
} | ConvertTo-Json
Invoke-RestMethod -Uri $WEBHOOK_LEAD -Method POST -ContentType "application/json" -Body $body
Write-Host ""
Start-Sleep -Seconds 3

Write-Host ""
Write-Host "[3.2] Diferente WID, mismo email - debe usar cliente existente por email..."
$body = @{
    whatsapp_id     = "+573999000002"
    email           = "francisco.cortazar@boats4u.co"
    nombre_full     = "Francisco Cortazar Alt"
    plan_id         = "atardecer_bahia"
    num_pax         = 2
    fecha_salida    = "2026-04-22"
    idioma          = "es"
    hora_salida_real = "17:00:00"
} | ConvertTo-Json
Invoke-RestMethod -Uri $WEBHOOK_LEAD -Method POST -ContentType "application/json" -Body $body
Write-Host ""
Start-Sleep -Seconds 3

Write-Host ""
Write-Host "[3.3] Cliente completamente nuevo..."
$body = @{
    whatsapp_id     = "+573999000003"
    email           = "nuevo.cliente@test.com"
    nombre_full     = "Cliente Nuevo Test"
    plan_id         = "atardecer_bahia"
    num_pax         = 3
    fecha_salida    = "2026-04-25"
    idioma          = "es"
    hora_salida_real = "17:00:00"
} | ConvertTo-Json
Invoke-RestMethod -Uri $WEBHOOK_LEAD -Method POST -ContentType "application/json" -Body $body
Write-Host ""
Start-Sleep -Seconds 3

Write-Host ""
Write-Host "[3.4] Cliente en ingles - idioma EN..."
$body = @{
    whatsapp_id     = "+13055550001"
    email           = "john.test@gmail.com"
    nombre_full     = "John Test"
    plan_id         = "atardecer_bahia"
    num_pax         = 2
    fecha_salida    = "2026-04-15"
    idioma          = "en"
    hora_salida_real = "17:00:00"
} | ConvertTo-Json
$resp4 = Invoke-RestMethod -Uri $WEBHOOK_LEAD -Method POST -ContentType "application/json" -Body $body
Write-Host "Response: $($resp4 | ConvertTo-Json -Compress)"
$LEAD_ID4 = $resp4.lead_id
Start-Sleep -Seconds 3

Write-Host ""
Write-Host "[3.5] Cotizar cliente EN - bravo_290..."
$body = @{
    whatsapp_id     = "+13055550001"
    email           = "john.test@gmail.com"
    bote_id         = "bravo_290"
    lead_id         = $LEAD_ID4
    plan_id         = "atardecer_bahia"
    num_pax         = 2
    fecha_salida    = "2026-04-15"
    idioma          = "en"
    hora_salida_real = "17:00:00"
    horas_extra     = 0
} | ConvertTo-Json
Invoke-RestMethod -Uri $WEBHOOK_COT -Method POST -ContentType "application/json" -Body $body
Write-Host ""
Start-Sleep -Seconds 3


# ============================================================
# GRUPO 4 — GRUPO GRANDE 15 PAX
# ============================================================

Write-Host ""
Write-Host "------------------------------------------------------------"
Write-Host " GRUPO 4 - GRUPO GRANDE 15 PAX"
Write-Host "------------------------------------------------------------"

Write-Host ""
Write-Host "[4.1] Registrar lead - 15 pax..."
$body = @{
    whatsapp_id     = "+573999000010"
    email           = "grupo.grande@test.com"
    nombre_full     = "Grupo Grande Test"
    plan_id         = "atardecer_bahia"
    num_pax         = 15
    fecha_salida    = "2026-03-31"
    idioma          = "es"
    hora_salida_real = "17:00:00"
} | ConvertTo-Json
$resp5 = Invoke-RestMethod -Uri $WEBHOOK_LEAD -Method POST -ContentType "application/json" -Body $body
Write-Host "Response: $($resp5 | ConvertTo-Json -Compress)"
$LEAD_ID5 = $resp5.lead_id
Start-Sleep -Seconds 3

Write-Host ""
Write-Host "[4.2] Cotizar - bravo_410 (15 pax)..."
$body = @{
    whatsapp_id     = "+573999000010"
    email           = "grupo.grande@test.com"
    bote_id         = "bravo_410"
    lead_id         = $LEAD_ID5
    plan_id         = "atardecer_bahia"
    num_pax         = 15
    fecha_salida    = "2026-03-31"
    idioma          = "es"
    hora_salida_real = "17:00:00"
    horas_extra     = 0
} | ConvertTo-Json
Invoke-RestMethod -Uri $WEBHOOK_COT -Method POST -ContentType "application/json" -Body $body
Write-Host ""


# ============================================================
# SQL VERIFICACION FINAL
# ============================================================

Write-Host ""
Write-Host "============================================================"
Write-Host " SQL VERIFICACION COMPLETA - Ejecutar en Supabase"
Write-Host "============================================================"

Write-Host ""
Write-Host "-- Vista general de todos los tests:"
Write-Host "SELECT c.whatsapp_id, c.nombre_full,"
Write-Host "       l.status_lead, l.bote_id,"
Write-Host "       cot.estado_cotizacion, cot.total_cotizado,"
Write-Host "       cot.temporada_aplicada, cot.numero_cotizacion,"
Write-Host "       cot.created_at"
Write-Host "FROM clients c"
Write-Host "JOIN leads l ON l.client_id = c.id"
Write-Host "LEFT JOIN cotizaciones cot ON cot.id = l.cotizacion_activa_id"
Write-Host "WHERE c.whatsapp_id IN ("
Write-Host "  '+573132488737','+573999000001','+573999000002',"
Write-Host "  '+573999000003','+13055550001','+573999000010'"
Write-Host ")"
Write-Host "ORDER BY cot.created_at DESC;"

Write-Host ""
Write-Host "-- Verificar superseded Grupo 1 (Francisco):"
Write-Host "SELECT numero_cotizacion, estado_cotizacion, total_cotizado, horas_extra, created_at"
Write-Host "FROM cotizaciones"
Write-Host "WHERE lead_id IN (SELECT id FROM leads WHERE whatsapp_id = '+573132488737')"
Write-Host "ORDER BY created_at ASC;"

Write-Host ""
Write-Host "-- Contar cotizaciones por estado:"
Write-Host "SELECT estado_cotizacion, COUNT(*) as total"
Write-Host "FROM cotizaciones"
Write-Host "GROUP BY estado_cotizacion;"

Write-Host ""
Write-Host "============================================================"
Write-Host " SQL LIMPIEZA - Ejecutar ANTES de re-correr el script"
Write-Host "============================================================"
Write-Host ""
Write-Host "DELETE FROM cotizaciones WHERE lead_id IN (SELECT id FROM leads WHERE whatsapp_id IN ('+573132488737','+573999000001','+573999000002','+573999000003','+13055550001','+573999000010'));"
Write-Host "DELETE FROM leads WHERE whatsapp_id IN ('+573132488737','+573999000001','+573999000002','+573999000003','+13055550001','+573999000010');"
Write-Host "DELETE FROM clients WHERE whatsapp_id IN ('+573132488737','+573999000001','+573999000002','+573999000003','+13055550001','+573999000010');"

Write-Host ""
Write-Host "============================================================"
Write-Host " TEST SUITE COMPLETO"
Write-Host "============================================================"
Write-Host ""
