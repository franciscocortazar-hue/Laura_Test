# Robot Laura — Claude Cowork
## Tu tarea: probar el comportamiento de Laura en Dapta

## URL del Playground
https://app.dapta.ai/agents-studio/text-agents/442b7400-8568-43e4-8887-2c5e60dc1ba5/playground

## Flujo
1. Abrir el Playground de Dapta
2. Para cada escenario en scenarios/COWORK_*.json:
   a. Nueva conversacion (boton refresh)
   b. Pegar el campo "mensaje" del JSON en el chat
   c. Enviar y esperar respuesta completa de Laura
   d. Evaluar cada assertion del JSON
   e. Registrar PASS o FAIL con la respuesta exacta
3. Generar reports/reporte_cowork_[timestamp].md

## Tipos de assertion
- "contiene": el texto de Laura debe incluir ese string
- "no_contiene": Laura NO debe incluir ese string
- "frase_prohibida": detectar frases de call center
- "tool_call": Laura debe haber ejecutado esa herramienta
- "idioma": verificar que Laura respondio en el idioma correcto

## Escenarios
| ID | Que prueba |
|---|---|
| T01_COWORK | Laura EN — saluda, registra, no pregunta datos |
| T02_COWORK | Laura ES — saluda en espanol, registra, recomienda bote |
| T06_COWORK | Fecha pasada — Laura la rechaza? |
| T10_COWORK | Mensaje resumen con link boats4u.lovable.app/cotizacion/[N] |

## Frases prohibidas a detectar
- "Procedemos a..."
- "Le informo que..."
- "Sin problema."
- "No worries at all."
- "[registrar_lead ejecutado]" → FAIL critico, Make fallo
- "[completar_bote_y_cotizar ejecutado]" → FAIL critico, Make fallo

## Notas
- Cada escenario = conversacion nueva (refresh)
- Timeout: si Laura no responde en 30s → FAIL
- T10 probablemente FALLA — el prompt v1.1 no tiene el mensaje resumen
  Eso es lo que queremos documentar como gap para v1.2
