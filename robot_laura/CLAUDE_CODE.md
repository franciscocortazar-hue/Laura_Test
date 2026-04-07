# Robot Laura — Claude Code
## Tu tarea: probar el motor Make + Supabase

Eres el tester del backend del sistema B4U. Dispara los webhooks de Make,
espera el procesamiento, y verifica en Supabase que los datos quedaron correctos.

## Webhooks de produccion
REGISTRAR_LEAD:
https://hook.us2.make.com/svepg2mtc1qwqe3fw5l9jvm26amdsxvx

COMPLETAR_BOTE_Y_COTIZAR:
https://hook.us2.make.com/qx52sszmy6g57a3mt2v524ttdefqm64t

## Supabase
SUPABASE_URL = "https://gqofyvvbmqnxpsgtwudq.supabase.co"
SUPABASE_SERVICE_ROLE_KEY = "PEGAR_AQUI"

CRITICO: Siempre usar service_role_key. El anon key no escribe (RLS sin policies).

## Tu flujo
1. Leer scenarios/CODE_*.json
2. Para cada escenario:
   a. Cleanup del WID de prueba en Supabase
   b. POST al webhook con el payload
   c. Esperar N segundos (campo espera_segundos)
   d. Verificar cada assertion en Supabase
   e. PASS o FAIL con evidencia
3. Generar reports/reporte_code_[timestamp].md

## Escenarios
T01 REGISTRAR_LEAD - Landing EN, cliente nuevo
T02 REGISTRAR_LEAD - Landing ES, cliente nuevo
T03 REGISTRAR_LEAD - Cliente existente mismo WID, no duplica
T04 REGISTRAR_LEAD - Cliente existente por email, Ruta 3
T05 COMPLETAR_BOTE_Y_COTIZAR - Temporada alta junio
T06 COMPLETAR_BOTE_Y_COTIZAR - Temporada baja agosto
T07 COMPLETAR_BOTE_Y_COTIZAR - 11 pax bravo_380
T08 COMPLETAR_BOTE_Y_COTIZAR - Superseded segunda cotizacion
T09 COMPLETAR_BOTE_Y_COTIZAR - Payload campo faltante

## Reglas criticas del sistema
- numero_cotizacion lo genera el TRIGGER PostgreSQL, Make nunca lo pasa
- bote_id en respuesta viene de BD (Lee Bote modulo 5), nunca del webhook
- Busca Lead Activo filtra SOLO por whatsapp_id, nunca por status_lead
- HTTP PATCH para updates parciales, nunca Upsert de Make

## Dependencias
pip install requests
