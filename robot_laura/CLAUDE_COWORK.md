# Robot Laura — Claude Cowork
## Tu tarea: probar el comportamiento de Laura en Dapta

Eres el tester conversacional. Abri el Playground de Dapta, envia mensajes
exactos que simulan lo que llega desde la landing de Lovable, y evalua
si Laura cumple los criterios definidos.

## URL del Playground
https://app.dapta.ai/agents-studio/text-agents/442b7400-8568-43e4-8887-2c5e60dc1ba5/playground

## Tu flujo
1. Abrir Playground de Dapta
2. Para cada escenario en scenarios/COWORK_*.json:
   a. Click en reset/nueva conversacion
   b. Copiar el campo "mensaje" del JSON
   c. Enviar y esperar respuesta completa de Laura
   d. Evaluar cada assertion del JSON
   e. PASS o FAIL con la respuesta exacta de Laura
3. Generar reports/reporte_cowork_[timestamp].md

## Escenarios
T01_COWORK Laura EN - landing completa - saluda, registra, no pregunta
T02_COWORK Laura ES - landing completa - responde en espanol
T06_COWORK Fecha pasada - Laura debe rechazarla
T10_COWORK Mensaje resumen con link - GAP CRITICO esperado

## Frases prohibidas en cualquier respuesta de Laura
- "Procedemos a..."
- "Le informo que..."
- "Sin problema."
- "Claro que si, con gusto."
- "No worries at all."
- "[registrar_lead ejecutado]" <- indica que Make fallo y Laura lo simulo
- "[completar_bote_y_cotizar ejecutado]" <- idem

## Formato del reporte
Para cada escenario: mensaje enviado, respuesta de Laura, assertions OK/FAIL
