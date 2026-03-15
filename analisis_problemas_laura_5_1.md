# Análisis de Problemas — Laura 5.1
**Fecha:** Marzo 2026
**Basado en:** Stress Test `test_laura2.py` contra `claude-sonnet-4-6`
**Resultado del test:** 7/13 escenarios PASS · 55/66 criterios (83%)

---

## Resumen Ejecutivo

El stress test reveló **3 categorías reales de fallo** en Laura 5.1 (más 1 falso negativo del script de prueba):

| # | Categoría | Escenarios afectados | Severidad |
|---|-----------|----------------------|-----------|
| 1 | Saludo bilingüe mezcla idiomas | A2, G1 | Media |
| 2 | Precios no disponibles en entorno de prueba | B1, D1 | Alta |
| 3 | Estrategia de cierre no se activa ante objeción | E1, G1 | **Crítica** |
| 4 | Falso negativo en script de test | A1 | Baja (script) |

---

## Problema 1 — Saludo bilingüe mezcla idiomas

### Escenarios fallidos: A2, G1 (parcial)

### Descripción
Cuando el cliente escribe en inglés, Laura abre con el saludo horario en español antes de cambiar al inglés en el resto del mensaje:

```
Laura: "¡Buenas noches! 🌊 Welcome to Boats4U..."
```

Esto rompe la regla de la Sección 0: *"Responde siempre en el idioma del cliente"*, ya que el saludo es la primera impresión.

### Causa Raíz
La Sección 9 define la tabla de saludos horarios únicamente en español:

```
| 05:00–11:59 | ¡Buen día!      |
| 12:00–18:59 | ¡Buenas tardes! |
| 19:00–04:59 | ¡Buenas noches! |
```

No existe variante en inglés ni instrucción de adaptar el saludo al idioma detectado. El modelo ejecuta el saludo horario en español por defecto antes de procesar el idioma del cliente.

### Solución
Agregar a la tabla de saludos (S.9) la variante en inglés y la regla de detección de idioma:

```
| Horario      | Español          | Inglés           |
|--------------|------------------|------------------|
| 05:00–11:59  | ¡Buen día!       | Good morning!    |
| 12:00–18:59  | ¡Buenas tardes!  | Good afternoon!  |
| 19:00–04:59  | ¡Buenas noches!  | Good evening!    |
```

Regla adicional:
> *Si el cliente escribe en inglés, usar exclusivamente la columna inglés. No mezclar idiomas en ningún turno, incluyendo el saludo.*

---

## Problema 2 — Precios no disponibles en entorno de prueba

### Escenarios fallidos: B1, D1

### Descripción
Laura recomienda la embarcación correcta pero no puede presentar el precio. Responde con frases evasivas:

```
Laura: "Déjame consultarte el precio oficial — ¿ya tienen fecha en mente?"
Laura: "El precio oficial para el 10 de abril te lo confirmo en un momento..."
```

El flujo comercial (S.11) requiere: recomendar → **presentar precio** → solicitar fecha. Al no poder presentar el precio, el flujo queda incompleto y Laura avanza al siguiente paso incorrectamente.

### Causa Raíz
La Sección 5 (Gobernanza de Información) instruye a Laura a usar **exclusivamente** precios del brain o Supabase. En entornos de prueba sin estas fuentes conectadas, Laura no tiene precios disponibles y no puede cumplir el flujo.

Esto no es un fallo del prompt de producción — es una limitación del entorno de prueba.

### Solución

**Para entorno de prueba:** Incluir una tabla de precios de referencia en el script de test (`test_laura2.py`) o en un archivo de contexto adicional que se pase como mensaje de sistema secundario.

Ejemplo de tabla a incluir en tests:
```
Precios de referencia (solo para pruebas):
- Golden Hour · Bravo 290 (1-5 pax): $850.000 COP
- Golden Hour · Firpol 34 (6-10 pax): $1.200.000 COP
- Islas del Rosario · Bravo 290: $1.100.000 COP
- Islas del Rosario · Firpol 34: $1.600.000 COP
- Islas del Rosario · Bravo 410: $2.400.000 COP
```

**Para producción:** Conectar el brain o Supabase con la tabla de precios oficial antes de activar Laura en canales reales.

---

## Problema 3 — Estrategia de cierre no se activa ante objeción (CRÍTICO)

### Escenarios fallidos: E1, G1

### Descripción
Este es el fallo más grave. Ante objeción de precio, Laura abandona la conversación completamente en lugar de activar la escalera de cierre definida en la Sección 16:

**Respuesta actual de Laura:**
```
"Sin problema, te entiendo perfectamente.
Si en algún momento las fechas se acomodan mejor o quieres explorar
algo más accesible, aquí estoy.
¿Hay algo más en lo que pueda ayudarte?"
```

**Problemas en esa respuesta:**
1. No activa Nivel 1 de cierre (*"Te recomiendo asegurarla hoy"*)
2. No activa Nivel 2 (*"Si quieres, te envío el link para asegurarla"*)
3. Termina con frase prohibida: *"¿En qué más le puedo ayudar?"* (S.4.1)
4. Interpreta la objeción como rechazo definitivo cuando no lo es

### Causa Raíz
La Sección 16 define los 3 niveles de cierre pero **no especifica cuándo activarlos** ante una objeción. Solo describe el contenido de cada nivel. El modelo interpreta la objeción de precio como fin de conversación por falta de instrucción explícita del trigger.

```
Sección 16 actual — solo define el contenido:
  Nivel 1: "Te recomiendo asegurarla hoy."
  Nivel 2: "Si quieres, te envío el link para asegurarla."
  Nivel 3: descuento 10% con condición de pago 100%
```

Falta la regla: **"ante objeción de precio → activar Nivel 1 de inmediato"**.

### Solución
Agregar al inicio de la Sección 16 una regla de activación obligatoria:

```markdown
### Regla de activación obligatoria
Ante cualquier objeción de precio (caro, no tengo presupuesto, es mucho,
déjame pensarlo, etc.):

1. NUNCA interpretar como rechazo definitivo.
2. NUNCA cerrar la conversación ni usar frases de despedida.
3. Activar Nivel 1 de inmediato.
4. Si la objeción persiste → activar Nivel 2.
5. Si la objeción persiste por segunda vez → activar Nivel 3 (una sola vez).
6. Solo cerrar si el cliente dice explícitamente que no quiere continuar.
```

---

## Problema 4 — Falso negativo en script de prueba (A1)

### Escenario: A1

### Descripción
El escenario A1 marca FAIL pero la respuesta de Laura es **correcta**:

```
Laura: "¡Buenas noches! 🌊 Bienvenido a Boats4U...
¿Cuál te llama más — el Golden Hour en bahía o un día completo en
Islas del Rosario?"
```

Laura usa el saludo correcto, emoji náutico, presenta ambas experiencias y cierra con la pregunta estratégica. El único fallo es el criterio `"No pregunta fecha en T1"` que tiene lógica invertida en el script.

### Causa Raíz
Error en `test_laura2.py` — el check verifica si Laura *no* pregunta fecha en T1, pero el resultado esperado era `True` (no pregunta) y el script estaba evaluando la condición incorrectamente.

### Solución
Corregir el check en el script de prueba. No requiere cambios en el prompt.

---

## Plan de Acción Priorizado

| Prioridad | Problema | Archivo a modificar | Esfuerzo |
|-----------|----------|---------------------|----------|
| 🔴 1 | Estrategia de cierre no activada | `LAURA_5_1.md` S.16 | Bajo |
| 🟠 2 | Saludo bilingüe mezcla idiomas | `LAURA_5_1.md` S.9 | Bajo |
| 🟡 3 | Precios en entorno de prueba | `test_laura2.py` + brain/Supabase | Medio |
| 🟢 4 | Falso negativo A1 | `test_laura2.py` | Bajo |

---

*Análisis generado con Claude Code · claude-sonnet-4-6 · Marzo 2026*
