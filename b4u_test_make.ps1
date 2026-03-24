# ============================================================
# B4U CRM — TEST SUITE MAKE (7 ESCENARIOS) — PowerShell
# 24 Marzo 2026
#
# COMO USAR:
#   .\b4u_test_make.ps1
# ============================================================

$WEBHOOK_LEAD = "https://hook.us2.make.com/svepg2mtc1qwqe3fw5l9jvm26amdsxvx"
$WEBHOOK_COT  = "https://hook.us2.make.com/qx52sszmy6g57a3mt2v524ttdefqm64t"
$WAIT = 5

function Send-Webhook($url, $body, $label) {
    Write-Host $label
    try {
        $resp = Invoke-RestMethod -Uri $url -Method Post -ContentType "application/json" -Body ($body | ConvertTo-Json -Depth 10)
        Write-Host "  OK: $resp"
    } catch {
        Write-Host "  HTTP $($_.Exception.Response.StatusCode.value__): $($_.Exception.Message)"
    }
    Start-Sleep -Seconds $WAIT
}

Write-Host ""
Write-Host "============================================================"
Write-Host " B4U CRM — TEST SUITE MAKE (7 ESCENARIOS)"
Write-Host " $(Get-Date)"
Write-Host "============================================================"

# --- ESCENARIO 1: CLIENTE NUEVO ---
Write-Host "`n--- ESCENARIO 1: CLIENTE NUEVO ---"

Send-Webhook $WEBHOOK_LEAD @{
    whatsapp_id = "+573101000001"; email = "ana.garcia@test.com"
    nombre_full = "Ana Garcia"; source = "landing"; tipo_plan = "atardecer_bahia"
    num_pax = 4; fecha_salida = "2026-04-15"; idioma = "es"
    payload = '{"full_name":"Ana Garcia","plan":"atardecer_bahia","preferred_date":"2026-04-15","passengers":4,"email":"ana.garcia@test.com","phone":"+573101000001","language":"es","source":"landing"}'
} "[1.1] Lead — Ana Garcia"

Send-Webhook $WEBHOOK_COT @{
    whatsapp_id = "+573101000001"; email = "ana.garcia@test.com"
    bote_id = "bravo_290"; plan_id = "atardecer_bahia"; num_pax = 4
    fecha_salida = "2026-04-15"; idioma = "es"; hora_salida_real = "17:00:00"; horas_extra = 0
} "[1.2] Cotizar bravo_290"

# --- ESCENARIO 2: RECOMPRA ---
Write-Host "`n--- ESCENARIO 2: RECOMPRA (Ana vuelve) ---"

Send-Webhook $WEBHOOK_LEAD @{
    whatsapp_id = "+573101000001"; email = "ana.garcia@test.com"
    nombre_full = "Ana Garcia"; source = "landing"; tipo_plan = "isla_del_sol"
    num_pax = 6; fecha_salida = "2026-05-10"; idioma = "es"
    payload = '{"full_name":"Ana Garcia","plan":"isla_del_sol","preferred_date":"2026-05-10","passengers":6,"email":"ana.garcia@test.com","phone":"+573101000001","language":"es","source":"landing"}'
} "[2.1] Lead recompra — Ana, isla_del_sol"

Send-Webhook $WEBHOOK_COT @{
    whatsapp_id = "+573101000001"; email = "ana.garcia@test.com"
    bote_id = "bravo_410"; plan_id = "isla_del_sol"; num_pax = 6
    fecha_salida = "2026-05-10"; idioma = "es"; hora_salida_real = "10:00:00"; horas_extra = 0
} "[2.2] Cotizar recompra bravo_410"

# --- ESCENARIO 3: DATOS ERRADOS ---
Write-Host "`n--- ESCENARIO 3: DATOS ERRADOS ---"

Send-Webhook $WEBHOOK_LEAD @{
    whatsapp_id = "+573102000001"; email = ""
    nombre_full = "Sin Email Test"; source = "landing"; tipo_plan = "atardecer_bahia"
    num_pax = 2; fecha_salida = "2026-04-20"; idioma = "es"
    payload = '{"full_name":"Sin Email Test","plan":"atardecer_bahia","preferred_date":"2026-04-20","passengers":2,"email":"","phone":"+573102000001","language":"es","source":"landing"}'
} "[3.1] Sin email"

Send-Webhook $WEBHOOK_LEAD @{
    whatsapp_id = "+573102000002"; email = "sin.nombre@test.com"
    nombre_full = ""; source = "landing"; tipo_plan = "atardecer_bahia"
    num_pax = 2; fecha_salida = "2026-04-20"; idioma = "es"
    payload = '{"full_name":"","plan":"atardecer_bahia","preferred_date":"2026-04-20","passengers":2,"email":"sin.nombre@test.com","phone":"+573102000002","language":"es","source":"landing"}'
} "[3.2] Sin nombre"

Send-Webhook $WEBHOOK_LEAD @{
    whatsapp_id = ""; email = "sin.wid@test.com"
    nombre_full = "Sin WID Test"; source = "landing"; tipo_plan = "atardecer_bahia"
    num_pax = 2; fecha_salida = "2026-04-20"; idioma = "es"
    payload = '{"full_name":"Sin WID Test","plan":"atardecer_bahia","preferred_date":"2026-04-20","passengers":2,"email":"sin.wid@test.com","phone":"","language":"es","source":"landing"}'
} "[3.3] Sin whatsapp_id"

Send-Webhook $WEBHOOK_LEAD @{
    whatsapp_id = "+573102000003"; email = "cero.pax@test.com"
    nombre_full = "Cero Pax Test"; source = "landing"; tipo_plan = "atardecer_bahia"
    num_pax = 0; fecha_salida = "2026-04-20"; idioma = "es"
    payload = '{"full_name":"Cero Pax Test","plan":"atardecer_bahia","preferred_date":"2026-04-20","passengers":0,"email":"cero.pax@test.com","phone":"+573102000003","language":"es","source":"landing"}'
} "[3.4] Num_pax = 0"

# --- ESCENARIO 4: COTIZACIÓN SIMPLE ---
Write-Host "`n--- ESCENARIO 4: COTIZACION SIMPLE ---"

Send-Webhook $WEBHOOK_LEAD @{
    whatsapp_id = "+573103000001"; email = "carlos.mendez@test.com"
    nombre_full = "Carlos Mendez"; source = "landing"; tipo_plan = "isla_del_sol"
    num_pax = 2; fecha_salida = "2026-04-18"; idioma = "es"
    payload = '{"full_name":"Carlos Mendez","plan":"isla_del_sol","preferred_date":"2026-04-18","passengers":2,"email":"carlos.mendez@test.com","phone":"+573103000001","language":"es","source":"landing"}'
} "[4.1] Lead — Carlos Mendez"

Send-Webhook $WEBHOOK_COT @{
    whatsapp_id = "+573103000001"; email = "carlos.mendez@test.com"
    bote_id = "bravo_290"; plan_id = "isla_del_sol"; num_pax = 2
    fecha_salida = "2026-04-18"; idioma = "es"; hora_salida_real = "10:00:00"; horas_extra = 0
} "[4.2] Cotizar bravo_290"

# --- ESCENARIO 5: 5 COTIZACIONES SEGUIDAS ---
Write-Host "`n--- ESCENARIO 5: 5 COTIZACIONES (superseded stress) ---"

Send-Webhook $WEBHOOK_LEAD @{
    whatsapp_id = "+573104000001"; email = "maria.lopez@test.com"
    nombre_full = "Maria Lopez"; source = "landing"; tipo_plan = "atardecer_bahia"
    num_pax = 2; fecha_salida = "2026-04-20"; idioma = "es"
    payload = '{"full_name":"Maria Lopez","plan":"atardecer_bahia","preferred_date":"2026-04-20","passengers":2,"email":"maria.lopez@test.com","phone":"+573104000001","language":"es","source":"landing"}'
} "[5.1] Lead — Maria Lopez"

Send-Webhook $WEBHOOK_COT @{
    whatsapp_id = "+573104000001"; email = "maria.lopez@test.com"
    bote_id = "bravo_290"; plan_id = "atardecer_bahia"; num_pax = 2
    fecha_salida = "2026-04-20"; idioma = "es"; hora_salida_real = "17:00:00"; horas_extra = 0
} "[5.2] Cot #1 — 2 pax, 0 extra"

Send-Webhook $WEBHOOK_COT @{
    whatsapp_id = "+573104000001"; email = "maria.lopez@test.com"
    bote_id = "bravo_290"; plan_id = "atardecer_bahia"; num_pax = 4
    fecha_salida = "2026-04-20"; idioma = "es"; hora_salida_real = "17:00:00"; horas_extra = 0
} "[5.3] Cot #2 — cambia a 4 pax"

Send-Webhook $WEBHOOK_COT @{
    whatsapp_id = "+573104000001"; email = "maria.lopez@test.com"
    bote_id = "bravo_290"; plan_id = "atardecer_bahia"; num_pax = 4
    fecha_salida = "2026-04-20"; idioma = "es"; hora_salida_real = "17:00:00"; horas_extra = 1
} "[5.4] Cot #3 — agrega 1 hora extra"

Send-Webhook $WEBHOOK_COT @{
    whatsapp_id = "+573104000001"; email = "maria.lopez@test.com"
    bote_id = "bravo_290"; plan_id = "atardecer_bahia"; num_pax = 4
    fecha_salida = "2026-04-02"; idioma = "es"; hora_salida_real = "17:00:00"; horas_extra = 1
} "[5.5] Cot #4 — fecha Semana Santa (alta)"

Send-Webhook $WEBHOOK_COT @{
    whatsapp_id = "+573104000001"; email = "maria.lopez@test.com"
    bote_id = "bravo_410"; plan_id = "atardecer_bahia"; num_pax = 4
    fecha_salida = "2026-04-02"; idioma = "es"; hora_salida_real = "17:00:00"; horas_extra = 2
} "[5.6] Cot #5 — bravo_410, 2 horas extra"

# --- ESCENARIO 6: CAMBIO DE PLAN ---
Write-Host "`n--- ESCENARIO 6: CAMBIO DE PLAN MID-FLOW ---"

Send-Webhook $WEBHOOK_LEAD @{
    whatsapp_id = "+573105000001"; email = "pedro.ruiz@test.com"
    nombre_full = "Pedro Ruiz"; source = "landing"; tipo_plan = "atardecer_bahia"
    num_pax = 2; fecha_salida = "2026-04-25"; idioma = "es"
    payload = '{"full_name":"Pedro Ruiz","plan":"atardecer_bahia","preferred_date":"2026-04-25","passengers":2,"email":"pedro.ruiz@test.com","phone":"+573105000001","language":"es","source":"landing"}'
} "[6.1] Lead — Pedro Ruiz, atardecer_bahia"

Send-Webhook $WEBHOOK_COT @{
    whatsapp_id = "+573105000001"; email = "pedro.ruiz@test.com"
    bote_id = "bravo_290"; plan_id = "atardecer_bahia"; num_pax = 2
    fecha_salida = "2026-04-25"; idioma = "es"; hora_salida_real = "17:00:00"; horas_extra = 0
} "[6.2] Cotizar atardecer_bahia"

Send-Webhook $WEBHOOK_COT @{
    whatsapp_id = "+573105000001"; email = "pedro.ruiz@test.com"
    bote_id = "bravo_410"; plan_id = "isla_del_sol"; num_pax = 8
    fecha_salida = "2026-04-25"; idioma = "es"; hora_salida_real = "10:00:00"; horas_extra = 0
} "[6.3] Cambia a isla_del_sol, bravo_410"

# --- ESCENARIO 7: DOBLE LEAD RÁPIDO ---
Write-Host "`n--- ESCENARIO 7: DOBLE LEAD RAPIDO ---"

$jobA = Start-Job -ScriptBlock {
    Invoke-RestMethod -Uri $using:WEBHOOK_LEAD -Method Post -ContentType "application/json" -Body (@{
        whatsapp_id = "+573106000001"; email = "lead.a@test.com"
        nombre_full = "Lead A Rapido"; source = "landing"; tipo_plan = "atardecer_bahia"
        num_pax = 2; fecha_salida = "2026-04-28"; idioma = "es"
        payload = '{"full_name":"Lead A Rapido","plan":"atardecer_bahia","preferred_date":"2026-04-28","passengers":2,"email":"lead.a@test.com","phone":"+573106000001","language":"es","source":"landing"}'
    } | ConvertTo-Json -Depth 10)
}
$jobB = Start-Job -ScriptBlock {
    Invoke-RestMethod -Uri $using:WEBHOOK_LEAD -Method Post -ContentType "application/json" -Body (@{
        whatsapp_id = "+573106000002"; email = "lead.b@test.com"
        nombre_full = "Lead B Rapido"; source = "landing"; tipo_plan = "isla_del_sol"
        num_pax = 3; fecha_salida = "2026-04-28"; idioma = "es"
        payload = '{"full_name":"Lead B Rapido","plan":"isla_del_sol","preferred_date":"2026-04-28","passengers":3,"email":"lead.b@test.com","phone":"+573106000002","language":"es","source":"landing"}'
    } | ConvertTo-Json -Depth 10)
}
Write-Host "[7.1] Lead A y [7.2] Lead B enviados simultaneo..."
Wait-Job $jobA, $jobB | Out-Null
Write-Host "  Lead A: $(Receive-Job $jobA)"
Write-Host "  Lead B: $(Receive-Job $jobB)"
Remove-Job $jobA, $jobB

Write-Host "`n============================================================"
Write-Host " TEST COMPLETO — $(Get-Date)"
Write-Host " Ahora corre los SELECT en Supabase para verificar"
Write-Host "============================================================"
