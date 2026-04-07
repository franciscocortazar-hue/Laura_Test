# Robot Laura — Claude Code
## Tu tarea: probar el motor Make + Supabase

Eres el tester del backend de B4U. Disparas webhooks de Make, esperas
procesamiento, y verificas en Supabase que los datos quedaron correctos.

## Webhooks de produccion
```
REGISTRAR_LEAD:
https://hook.us2.make.com/svepg2mtc1qwqe3fw5l9jvm26amdsxvx

COMPLETAR_BOTE_Y_COTIZAR:
https://hook.us2.make.com/qx52sszmy6g57a3mt2v524ttdefqm64t
```

## Supabase
```
SUPABASE_URL = "https://gqofyvvbmqnxpsgtwudq.supabase.co"
SUPABASE_SERVICE_ROLE_KEY = "PEGAR_AQUI"
```
CRITICO: Siempre service_role_key. El anon key no escribe nada (RLS).

## Flujo
1. Leer scenarios/CODE_*.json
2. Por cada escenario: cleanup → POST webhook → esperar → verificar Supabase
3. Generar reports/reporte_code_[timestamp].md

## Escenarios
| ID | Webhook | Que prueba |
|---|---|---|
| T01 | REGISTRAR_LEAD | Landing EN — cliente nuevo |
| T02 | REGISTRAR_LEAD | Landing ES — cliente nuevo |
| T03 | REGISTRAR_LEAD | Cliente existente mismo WID — no duplica |
| T04 | REGISTRAR_LEAD | Cliente existente por email diferente WID |
| T05 | COMPLETAR_BOTE_Y_COTIZAR | Temporada alta — precio correcto |
| T06 | COMPLETAR_BOTE_Y_COTIZAR | Temporada baja — precio correcto |
| T07 | COMPLETAR_BOTE_Y_COTIZAR | 11 pax → bravo_380 |
| T08 | COMPLETAR_BOTE_Y_COTIZAR | Superseded — segunda cotizacion |
| T09 | COMPLETAR_BOTE_Y_COTIZAR | Payload con campo faltante |

## Notas criticas
- numero_cotizacion lo genera el TRIGGER PostgreSQL — Make nunca lo pasa
- bote_id en respuesta viene de {{5.id}} (Lee Bote en BD)
- Busca Lead Activo filtra SOLO por whatsapp_id — nunca por status_lead
- WIDs de prueba: siempre +1780999000X — nunca numeros reales

## Dependencias
pip install requests
