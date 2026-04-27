# COWORK 1.0 — Conciliación facturas combustible Nautiturismo → Todomar

> **Ejecutor**: Claude Cowork (este prompt está escrito como instrucciones operativas para que Claude Cowork las ejecute).

## Objetivo
Procesar de forma autónoma los correos de facturación electrónica recibidos en la bandeja de **Todomar CHL S.A.S.** (NIT 806003144) que contienen facturas de combustible emitidas por **Nautiturismo SAS** (NIT 901459048) a través de Facture:

1. Descargar adjuntos (ZIPs) desde Gmail.
2. Organizarlos en disco por número de factura.
3. Extraer datos de los PDFs (factura y remisión).
4. Conciliar valor factura vs valor remisión.
5. Reportar el resultado en un archivo de control nuevo, bien organizado.

---

## Rutas en disco (G:)

| Concepto | Ruta |
|---|---|
| Carpeta de facturas (una subcarpeta por factura) | `G:\Mi unidad\Inteligencia Artificial\Productividad\Gasolina\Facturas\` |
| Carpeta del archivo de control (lo crea Cowork) | `G:\Mi unidad\Inteligencia Artificial\Productividad\Gasolina\Control\` |
| Carpeta de excepciones (auditoría — emisor distinto) | `G:\Mi unidad\Inteligencia Artificial\Productividad\Gasolina\No_Aplica\` |
| Excel fuente (referencia de qué facturas esperar) | `G:\Mi unidad\Inteligencia Artificial\Productividad\Gasolina\DETALLE FACTURAS COMBUSTIBLES ENERO A ABRIL 24-2026.xlsx` |

---

## Entradas

### A) Cuenta Gmail
- Cuenta corporativa de **Todomar CHL S.A.S.** (NIT 806003144).
- **Filtro remitente**: `from:no-responder@facture.co` (plataforma de facturación electrónica usada por Nautiturismo).
- **Filtro asunto**: el formato estándar es
  ```
  <NIT_receptor>;<RAZON_receptor>;FC<NUMDOCTRA>;<seq>;<RAZON_receptor>
  ```
  Ejemplo real:
  ```
  806003144;TODOMAR CHL S.A.S.;FC80230;01;TODOMAR CHL S.A.S
  ```
  Filtrar por correos cuyo asunto contenga `TODOMAR CHL S.A.S.` y un segmento `FC<digits>`.
- **Rango de fechas**: configurable. Para esta corrida: **2026-01-01 a 2026-04-30**.
- **Adjuntos**: cada correo trae un ZIP con uno o más PDFs (factura + remisión(es)).
- **Aviso**: la cuenta de Todomar solo recibe por Facture facturas de Nautiturismo (confirmado por el usuario). De todas formas Cowork hace una verificación silenciosa del NIT del emisor en el PDF de la factura como auditoría defensiva: si alguna vez aparece un emisor distinto, lo loggea y lo aparta a la carpeta de excepciones (ver Paso 2).

### B) Excel fuente (solo lectura — referencia)
- Hoja: `Hoja1`
- 114 facturas, fila 1 cabeceras, fila 2 leyenda explicativa de las columnas de conciliación, datos desde fila 3.
- Columnas relevantes:
  - Col 6 `NUMDOCTRA` → número de factura (ej. `74783` → carpeta `FC74783`)
  - Col 9 `VALORTRA` → valor facturado de referencia
  - Cols 1-10 → datos contables que se copian al archivo de control

### C) Archivo de control (salida — lo crea Cowork)
- Ruta: `G:\Mi unidad\Inteligencia Artificial\Productividad\Gasolina\Control\Control_Conciliacion_Combustibles.xlsx`
- Si ya existe → sobreescribir actualizando filas existentes y agregando nuevas.
- Estructura: ver sección **Estructura del archivo de control** más abajo.

---

---

## Modos de ejecución

Cowork acepta el parámetro `LIMITE_CORREOS`:

| Valor | Comportamiento |
|---|---|
| `LIMITE_CORREOS = 2` | **Modo prueba** — procesa solo los **2 correos más antiguos** del filtro Gmail (los primeros 2 de enero 2026). Útil para validar el pipeline antes del lote completo. |
| `LIMITE_CORREOS = 0` o sin definir | **Modo lote completo** — procesa todos los correos que pasen el filtro en el rango de fechas. |

**Plan recomendado:**
1. Primera corrida: `LIMITE_CORREOS = 2`. Revisar manualmente la carpeta `FC<num>\` y la fila correspondiente del archivo de control.
2. Si todo cuadra: correr de nuevo con `LIMITE_CORREOS = 0` para procesar el resto. La idempotencia garantiza que las 2 carpetas ya creadas no se reprocesan.

---

## Flujo

### Paso 1 — Descarga de correos
Para cada correo que pase el filtro Gmail:
1. Parsear el asunto para extraer `NUMDOCTRA`:
   ```
   asunto.split(';')[2]   →   "FC80230"
   strip prefijo "FC"      →   NUMDOCTRA = 80230
   ```
   (alternativamente regex `FC(\d+)` sobre el asunto).
2. Si el `NUMDOCTRA` **no está** en la lista de las 114 facturas del Excel fuente → loggear como "factura no esperada" y saltar (no procesar).
3. Descargar **cada ZIP adjunto** a una carpeta temporal de staging.
4. Conservar el `Message-ID` y asunto completo para trazabilidad.
5. (Recomendado) aplicar etiqueta Gmail `Procesado/Nautiturismo` al correo para idempotencia entre corridas.

### Paso 2 — Por cada ZIP descargado
1. Crear carpeta destino:
   ```
   G:\Mi unidad\Inteligencia Artificial\Productividad\Gasolina\Facturas\FC<NUMDOCTRA>\
   ```
2. **Idempotencia**: si la carpeta ya existe Y contiene `FAC-FC<NUMDOCTRA>.pdf`, saltar este ZIP (ya procesado en una corrida anterior). Loggear como duplicado.
3. Descomprimir el ZIP dentro de la carpeta.
4. Identificar y renombrar los PDFs (filenames auto-descriptivos):
   - El PDF firmado por la DIAN (con CUFE / código QR de validación) → **`FAC-FC<NUMDOCTRA>.pdf`**
   - El/los PDF(s) de despacho (encabezado "REMISIÓN" o similar, traen nombre del bote):
     - Si hay 1 sola → **`REM-FC<NUMDOCTRA>.pdf`**
     - Si hay N≥2 → **`REM-FC<NUMDOCTRA>_1.pdf`, `REM-FC<NUMDOCTRA>_2.pdf`, ...**
5. **Validar emisor (auditoría)**: abrir el PDF de la factura y confirmar que el emisor es `NAUTITURISMO SAS` (NIT `901459048`). Si no lo es → mover la carpeta completa a `G:\Mi unidad\Inteligencia Artificial\Productividad\Gasolina\No_Aplica\FC<NUMDOCTRA>\` y loggear "emisor distinto, apartado". (Caso esperado: nunca debería ocurrir; se deja como red de seguridad).

### Paso 3 — Extraer datos de los PDFs
- De **`FAC-FC<NUMDOCTRA>.pdf`**:
  - `valor_factura` (valor total de la factura)
- De **cada `REM-FC<NUMDOCTRA>*.pdf`** (si existen):
  - `valor_remision_i`
  - `nombre_bote` (literal lo que aparezca: "B10", "B5", "Lemarie", etc.)
  - `fecha_hora_tanqueo` (timestamp del despacho)

> Si las remisiones tienen distintos botes para una misma factura, registrar todos los nombres separados por coma en la celda `Nombre de Bote`.

### Paso 4 — Conciliación

#### 4.1 Estrategia de extracción del valor (con fallback)

Para leer el `valor_remision` de un PDF de remisión, aplicar en orden:

1. **`pdfplumber`** sobre el PDF — funciona si el PDF es digital (texto seleccionable).
2. **OCR (tesseract)** sobre la imagen — funciona en escaneos limpios.
3. **Visión multimodal** (Claude Vision API si es Python; visión nativa de Cowork si es Cowork) — leer la imagen directamente con un modelo que tolera ruido. Maneja recibos POS escaneados borrosos.
4. **Fallback final** → marcar como **`Pendiente revisión manual`** (ver lógica abajo).

Aplicar en orden: si la opción 1 da un número plausible (entero, en rango razonable), parar. Si no, intentar 2. Y así.

#### 4.2 Lógica de conciliación

```
SI no existe ningún REM-FC<NUMDOCTRA>*.pdf:
    Conciliacion       = "No hay remisión"
    Valor              = (vacío)
    Nombre de Bote     = (vacío)
    Fecha y hora       = (vacío)

SI existe(n) remisión(es) PERO el valor NO se pudo extraer
   (los 3 métodos fallaron):
    Conciliacion       = "Pendiente revisión manual (OCR no concluyente)"
    Valor              = (vacío)
    Nombre de Bote     = (lo que se haya podido leer del filename o PDF)
    Fecha y hora       = (lo que se haya podido leer)

SI existe 1 sola REM-FC<NUMDOCTRA>.pdf con valor extraíble:
    diferencia = valor_factura - valor_remision
    SI |diferencia| <= 1000:
        Conciliacion = "OK"
        Valor        = 0
    SI NO:
        Conciliacion = "Remisión con valor diferente"
        Valor        = diferencia            (con signo)

SI existen N remisiones (N >= 2) con TODOS los valores extraíbles:
    suma_remisiones = sum(valor_remision_i)
    diferencia      = valor_factura - suma_remisiones
    SI |diferencia| <= 1000:
        Conciliacion = "OK"
        Valor        = 0
    SI NO:
        Conciliacion = "Remisión con valor diferente (" + N + " remisiones, no coincide con el valor facturado)"
        Valor        = diferencia            (con signo)

SI existen N remisiones (N >= 2) y al menos UNA no se pudo extraer:
    Conciliacion       = "Pendiente revisión manual (1 de N remisiones no legible)"
    Valor              = (vacío)
```

**Tolerancia**: ±$1.000 (mil pesos) absorbe redondeos. Dentro de eso → OK.

**Convención de signo en `Valor`**:
- **Positivo** → factura > remisión → diferencia a favor de **Nautiturismo** (les cobraron de más a Todomar).
- **Negativo** → factura < remisión → diferencia a favor de **Todomar** (despacharon de más).

### Paso 5 — Verificación cruzada (auditoría interna)
- Si `valor_factura` extraído del PDF **difiere** de `VALORTRA` del Excel fuente → loggear como inconsistencia en la hoja `Log` del archivo de control. No detiene el flujo.

### Paso 6 — Escribir archivo de control

El archivo de control siempre refleja el **universo completo** (las 114 facturas del Excel fuente), no solo las que se procesaron en la corrida actual. Esto da una vista única, siempre comparable, donde se ve de inmediato qué está pendiente.

**Si el archivo NO existe (primera corrida):**
1. Crear `Control_Conciliacion_Combustibles.xlsx` en `G:\...\Gasolina\Control\`.
2. **Bootstrap**: leer las 114 filas del Excel fuente (`DETALLE FACTURAS COMBUSTIBLES ENERO A ABRIL 24-2026.xlsx`, hoja `Hoja1`, filas 3-116) y volcar en la hoja `Conciliación` las columnas A-F (NUMDOCTRA, Fecha, Razón social, NIT, Tipo doc, Valor factura).
3. Las columnas G-O quedan vacías en este momento (se mostrarán como "pendiente" en el Resumen).
4. Aplicar formato (cabeceras, filtros, formato condicional, moneda COP).

**Para cada factura procesada en la corrida (sea la 1ª o la N-ésima):**
1. Buscar la fila por `NUMDOCTRA` en la hoja `Conciliación`.
2. Llenar las columnas G-O con los datos extraídos / calculados.
3. Si el `NUMDOCTRA` no existe en la hoja (factura no esperada) → loggear y NO crear fila nueva.

**Al final de cada corrida:**
- Recalcular la hoja `Resumen` con los totales actualizados (procesadas vs pendientes, etc.).
- Agregar una entrada nueva a la hoja `Log`.

**Consecuencia para el modo prueba (LIMITE_CORREOS = 2):**
La primera corrida crea el archivo con las **114 filas listadas**, pero solo **2** tendrán las columnas G-O llenas. Las otras 112 filas mostrarán cols G-O vacías → en `Resumen` aparecen como "Facturas pendientes (sin correo) = 112". Es así como debe quedar.

---

## Estructura del archivo de control

**Archivo**: `Control_Conciliacion_Combustibles.xlsx`

### Hoja 1 — `Conciliación` (detalle por factura)

> **114 filas siempre presentes** — una por factura del alcance, copiadas del Excel fuente al crear el archivo. Las columnas A-F se llenan en el bootstrap inicial; las columnas G-O se van completando a medida que Cowork procesa correos. Una factura "pendiente" se ve como la fila con A-F llenas y G-O vacías.

| Col | Cabecera | Origen | Notas |
|---|---|---|---|
| A | NUMDOCTRA | Excel fuente | clave única |
| B | Fecha factura | Excel fuente (`FECHATRA`) | |
| C | Razón social | Excel fuente (`RAZONCIAL`) | |
| D | NIT | Excel fuente (`IDTERCERO`) | |
| E | Tipo doc | Excel fuente (`TIPOFAC` + `IDFUENTE`) | "FC" |
| F | Valor factura ($) | Excel fuente (`VALORTRA`) | formato moneda COP |
| G | Nombre de Bote | Cowork (de la remisión) | "B10" / "B5" / "Lemarie" / etc. |
| H | Fecha y hora de tanqueo | Cowork (de la remisión) | |
| I | Valor remisión ($) | Cowork (suma si N≥2) | |
| J | # Remisiones | Cowork | 0, 1, 2, ... |
| K | Conciliación | Cowork | OK / No hay remisión / Remisión con valor diferente (...) |
| L | Valor (diferencia $) | Cowork | con signo, 0 si OK |
| M | Link factura | Cowork | **Hipervínculo clicable** que abre el PDF al hacer clic. URL: `file:///G:/Mi unidad/Inteligencia Artificial/Productividad/Gasolina/Facturas/FC<num>/FAC-FC<num>.pdf`. Texto visible: `FAC-FC<num>.pdf`. Estilo: azul subrayado. |
| N | Link remisión(es) | Cowork | **Hipervínculo clicable** que abre el PDF al hacer clic. <br>**Caso 1 remisión** → URL: `file:///.../FC<num>/REM-FC<num>.pdf`, texto visible: `REM-FC<num>.pdf`. <br>**Caso N≥2 remisiones** (Excel solo soporta 1 hipervínculo por celda) → URL: `file:///.../FC<num>/` (apunta a la **carpeta**, al hacer clic se abre el explorador con todas las remisiones), texto visible: `Carpeta (N remisiones)`. <br>**Caso sin remisión** → vacío. |
| O | Última actualización | Cowork | timestamp de la corrida que tocó la fila |

**Formato:**
- Fila 1: cabeceras en negrita, fondo gris claro, panel inmovilizado.
- Auto-filtro habilitado en toda la tabla.
- Formato condicional en columna **K (Conciliación)**:
  - Verde claro → `OK`
  - Amarillo → `No hay remisión`
  - Rojo claro → empieza con `Remisión con valor diferente`
  - Naranja → empieza con `Pendiente revisión manual` (acción humana requerida)
- Formato condicional en columna **L (Valor)**:
  - Rojo si > 1000 (a favor Nautiturismo, revisar)
  - Naranja si < -1000 (a favor Todomar, revisar)
- Columnas F, I, L con formato moneda COP `$#,##0;[Red]-$#,##0`.
- Anchos de columna ajustados al contenido.

### Hoja 2 — `Resumen` (KPIs)

| Métrica | Valor |
|---|---|
| Total facturas en alcance | 114 |
| Total facturado ($) | $70.512.720,52 |
| **Conciliación** | |
| OK | conteo + $ |
| Sin remisión | conteo + $ |
| Con diferencia | conteo + suma de Valor (con signo) |
| Pendiente revisión manual | conteo + $ facturado (sin valor diferencia, queda para ojo humano) |
| **Diferencias** | |
| A favor de Nautiturismo (Valor > 0) | conteo + suma $ |
| A favor de Todomar (Valor < 0) | conteo + suma $ |
| Neto de diferencias | suma algebraica $ |
| **Cobertura** | |
| Facturas procesadas | conteo + % |
| Facturas pendientes (sin correo) | conteo + % |

### Hoja 3 — `Log` (auditoría de corridas)

Una fila por cada corrida de Cowork:

| Timestamp | Correos leídos | ZIPs descargados | Facturas nuevas | Facturas saltadas (duplicadas) | Errores | Inconsistencias factura↔Excel | Detalle |
|---|---|---|---|---|---|---|---|

---

## Casos de borde

| Caso | Acción |
|---|---|
| ZIP corrupto o sin PDFs | `Conciliación = "ZIP inválido"`, registrar en Log, no abortar el lote. |
| Factura del correo sin fila en el Excel fuente | Log: "factura no esperada". Crear carpeta y guardar PDFs igual, pero no agregar fila al control. |
| Fila en el Excel fuente sin correo recibido | Queda con cols G-O vacías. Aparece en `Resumen` como "pendiente". |
| Dos PDFs sin distinción clara factura/remisión | Priorizar: el que tiene CUFE/QR de la DIAN es la factura. Si ambos o ninguno tienen CUFE → registrar error y dejar la carpeta sin renombrar. |
| Mismo `NUMDOCTRA` en dos correos distintos | Procesar una sola vez (idempotencia por carpeta existente). Loggear como duplicado. |
| Múltiples remisiones con botes distintos | Listar todos los botes separados por coma en col G. Sumar valores como dice la lógica. |

---

## Resumen ejecutivo (1 frase)

> "Cowork lee los correos de Nautiturismo, descarga los ZIPs, los descomprime en carpetas `FC<numero>` (una por factura) bajo `G:\...\Facturas\`, compara el valor de la factura con el de la remisión (sumando si hay varias), y escribe el resultado en `G:\...\Control\Control_Conciliacion_Combustibles.xlsx`: OK si están dentro de $1.000 de diferencia, o reporta la diferencia con signo (positivo a favor Nautiturismo, negativo a favor Todomar) si no concilian. Si no llegó remisión, lo marca como 'No hay remisión'."
