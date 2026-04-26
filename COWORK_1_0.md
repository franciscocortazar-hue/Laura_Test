# COWORK 1.0 — Conciliación facturas combustible Nautiturismo → Todomar

## Objetivo
Procesar de forma autónoma los correos de **Nautiturismo SAS** (NIT 901459048) que contienen facturas de combustible para los botes de **Todomar**:

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
| Excel fuente (referencia de qué facturas esperar) | `G:\Mi unidad\Inteligencia Artificial\Productividad\Gasolina\DETALLE FACTURAS COMBUSTIBLES ENERO A ABRIL 24-2026.xlsx` |

---

## Entradas

### A) Cuenta Gmail
- Cuenta corporativa que recibe los correos de Nautiturismo.
- **Filtro remitente**: `from:` del correo conocido del proveedor (NIT 901459048).
- **Rango de fechas**: configurable. Para esta corrida: **2026-01-01 a 2026-04-30**.
- **Adjuntos**: cada correo trae un ZIP con uno o más PDFs (factura + remisión(es)).

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

## Flujo

### Paso 1 — Descarga de correos
Para cada correo de Nautiturismo en el rango configurado:
1. Descargar **cada ZIP adjunto** a una carpeta temporal de staging.
2. Conservar el `Message-ID` y asunto para trazabilidad.
3. (Recomendado) aplicar etiqueta Gmail `Procesado/Nautiturismo` para idempotencia entre corridas.

### Paso 2 — Por cada ZIP descargado
1. Identificar el **número de factura** (`NUMDOCTRA`):
   - Primero del nombre del archivo si lo trae (ej. `FE74783.zip`, `FC74783.zip`).
   - Si no, abrir un PDF, leerlo y buscar el número en el cuerpo de la factura electrónica.
2. Crear carpeta destino:
   ```
   G:\Mi unidad\Inteligencia Artificial\Productividad\Gasolina\Facturas\FC<NUMDOCTRA>\
   ```
3. **Idempotencia**: si la carpeta ya existe Y contiene `factura.pdf`, saltar este ZIP (ya procesado en una corrida anterior). Loggear como duplicado.
4. Descomprimir el ZIP dentro de la carpeta.
5. Renombrar los PDFs:
   - El PDF firmado por la DIAN (con CUFE / código QR de validación) → **`factura.pdf`**
   - El/los PDF(s) de despacho (encabezado "REMISIÓN" o similar, traen nombre del bote) → **`remision.pdf`** si hay una sola, o **`remision_1.pdf`, `remision_2.pdf`, ...** si hay varias.

### Paso 3 — Extraer datos de los PDFs
- De **`factura.pdf`**:
  - `valor_factura` (valor total de la factura)
- De **cada `remision*.pdf`** (si existen):
  - `valor_remision_i`
  - `nombre_bote` (literal lo que aparezca: "B10", "B5", "Lemarie", etc.)
  - `fecha_hora_tanqueo` (timestamp del despacho)

> Si las remisiones tienen distintos botes para una misma factura, registrar todos los nombres separados por coma en la celda `Nombre de Bote`.

### Paso 4 — Conciliación

```
SI no existe ninguna remision*.pdf:
    Conciliacion       = "No hay remisión"
    Valor              = (vacío)
    Nombre de Bote     = (vacío)
    Fecha y hora       = (vacío)

SI existe 1 sola remision.pdf:
    diferencia = valor_factura - valor_remision
    SI |diferencia| <= 1000:
        Conciliacion = "OK"
        Valor        = 0
    SI NO:
        Conciliacion = "Remisión con valor diferente"
        Valor        = diferencia            (con signo)

SI existen N remisiones (N >= 2):
    suma_remisiones = sum(valor_remision_i)
    diferencia      = valor_factura - suma_remisiones
    SI |diferencia| <= 1000:
        Conciliacion = "OK"
        Valor        = 0
    SI NO:
        Conciliacion = "Remisión con valor diferente (" + N + " remisiones, no coincide con el valor facturado)"
        Valor        = diferencia            (con signo)
```

**Tolerancia**: ±$1.000 (mil pesos) absorbe redondeos. Dentro de eso → OK.

**Convención de signo en `Valor`**:
- **Positivo** → factura > remisión → diferencia a favor de **Nautiturismo** (les cobraron de más a Todomar).
- **Negativo** → factura < remisión → diferencia a favor de **Todomar** (despacharon de más).

### Paso 5 — Verificación cruzada (auditoría interna)
- Si `valor_factura` extraído del PDF **difiere** de `VALORTRA` del Excel fuente → loggear como inconsistencia en la hoja `Log` del archivo de control. No detiene el flujo.

### Paso 6 — Escribir archivo de control
Ver sección siguiente para la estructura. Cowork:
- Crea el archivo si no existe.
- Si ya existe, actualiza la fila correspondiente por `NUMDOCTRA` (no duplica).
- Recalcula la hoja `Resumen` con los totales actualizados.
- Agrega una entrada nueva a la hoja `Log` por cada corrida.

---

## Estructura del archivo de control

**Archivo**: `Control_Conciliacion_Combustibles.xlsx`

### Hoja 1 — `Conciliación` (detalle por factura)

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
| M | Link factura | Cowork | hipervínculo a `G:\...\FC<num>\factura.pdf` |
| N | Link remisión(es) | Cowork | hipervínculo (si N≥2, listar separados por `;`) |
| O | Última actualización | Cowork | timestamp de la corrida que tocó la fila |

**Formato:**
- Fila 1: cabeceras en negrita, fondo gris claro, panel inmovilizado.
- Auto-filtro habilitado en toda la tabla.
- Formato condicional en columna **K (Conciliación)**:
  - Verde claro → `OK`
  - Amarillo → `No hay remisión`
  - Rojo claro → empieza con `Remisión con valor diferente`
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
