# MANUAL DE OPERACIÓN — Conciliador de combustible

> Cómo correr, validar, y generar informes a partir del conciliador.
> Para setup inicial (instalar Python, OAuth, credentials.json, etc.) ver [`README.md`](./README.md).

---

## Resumen del flujo

```
┌─────────────────────────────────────────────────────────────┐
│                                                             │
│   1. PREPARAR     →  Configurar período, snapshot          │
│                                                             │
│   2. PROCESAR     →  Dry-run + lote real                   │
│                                                             │
│   3. VALIDAR      →  Abrir Excel, revisar 🔴 y 🟠          │
│                                                             │
│   4. CORREGIR     →  Reprocesar fallos puntuales           │
│                                                             │
│   5. INFORME      →  Email a Nautiturismo (manual)         │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## 1. Procesar un nuevo período (por ejemplo: un año completo)

### 1.1 Configurar el rango de fechas

Editar `.env`:

```bash
cd ~/Downloads/Laura_Test/conciliador
vi .env
```

Cambiar:
```
DATE_FROM=2026-01-01
DATE_TO=2026-12-31
```

(O usar flags `--since 2026-01-01 --until 2026-12-31` al correr para overrideear sin tocar el `.env`.)

### 1.2 Verificar que el Excel fuente cubra el período

El archivo `DETALLE FACTURAS COMBUSTIBLES <PERIODO>.xlsx` (en `G:\...\Gasolina\`) define el universo de facturas esperadas. Si vas a procesar un período que el Excel actual no cubre:

- Opción A: actualizar el Excel maestro para que incluya las nuevas facturas del periodo
- Opción B: usar un Excel maestro diferente y ajustar `SOURCE_EXCEL` en `.env`

Las facturas que no estén en el Excel se loggean como `numdoctra_not_expected` y **no se escriben al control** (sí se descarga el ZIP igual, queda en `Facturas/FC<num>/` para auditoría).

### 1.3 Snapshot defensivo (recomendado antes de cada lote grande)

```bash
GASOLINA="/c/Users/franc/Mi unidad/Inteligencia Artificial/Productividad/Gasolina"
SNAPSHOT="$GASOLINA/_snapshots/$(date +%Y%m%d_%H%M)_pre_lote"
mkdir -p "$SNAPSHOT"
cp -r "$GASOLINA/Facturas" "$SNAPSHOT/" 2>/dev/null
cp "$GASOLINA/Control/Control_Conciliacion_Combustibles.xlsx" "$SNAPSHOT/" 2>/dev/null
echo "✓ Snapshot guardado en $SNAPSHOT"
```

Si algo sale mal, restauras desde ahí.

### 1.4 Dry-run de prueba (no descarga, solo lista)

```bash
source .venv/Scripts/activate
python conciliador.py --dry-run --limit 5
```

Verifica que el filtro Gmail funciona y los NUMDOCTRA que se extraen coinciden con lo esperado.

### 1.5 Procesar el lote real

```bash
python conciliador.py
```

Tarda ~3-10 segundos por factura (mayoría es la llamada a Claude Vision para remisiones escaneadas). Para 118 facturas: ~5-10 min.

**Costo aproximado**: $0.008 × N facturas. Para un año (~1.500 facturas): ~$12 USD.

---

## 2. Validar el resultado

Abrir `Control_Conciliacion_Combustibles.xlsx`, hoja **Conciliación**.

### 2.1 Filtrar por estado (col K)

Click en la flecha de filtro de la cabecera **Conciliación** y filtra por:

| Estado | Color | Acción |
|---|---|---|
| 🟢 OK | Verde | Nada — ya están cuadradas |
| 🟡 No hay remisión | Amarillo | Apuntar para reclamar a Nautiturismo |
| 🔴 Remisión con valor diferente | Rojo | Verificar manualmente abriendo factura y remisión |
| 🟠 Pendiente revisión manual | Naranja | Vision falló — verificar y corregir manualmente |

### 2.2 Verificar las 🔴 y 🟠 una por una

Para cada fila marcada en rojo o naranja:

1. Click en col **M (Link factura)** → abre el PDF de la factura → confirma valor
2. Click en col **N (Link remisión)** → abre el PDF de la remisión → confirma valor
3. Compara visualmente

**Si Vision leyó mal**:
- Anota el valor correcto
- Reprocesa esa factura puntualmente (ver sección 3.1)

**Si la diferencia es real**:
- Es para reclamar (o explicar) al proveedor
- Apuntar para el informe

### 2.3 Verificar los 🟡 (sin remisión)

Para cada uno:
1. Confirmar que el correo en Gmail efectivamente llegó **sin** remisión interna
2. Si sí venía la remisión y el script no la encontró, es bug — pegar evidencia en sesión Claude
3. Si efectivamente no vino remisión → reclamar al proveedor

---

## 3. Operaciones comunes

### 3.1 Reprocesar UNA factura específica (ej. FC74783)

Útil cuando Vision lee mal o quieres rehacer una sola.

```bash
GASOLINA="/c/Users/franc/Mi unidad/Inteligencia Artificial/Productividad/Gasolina"

# 1. Borrar la carpeta (la idempotencia se basa en existencia de FAC-FC<num>.pdf)
rm -rf "$GASOLINA/Facturas/FC74783"

# 2. Cerrar Excel si está abierto, borrar lock file
rm -f "$GASOLINA/Control/~\$Control_Conciliacion_Combustibles.xlsx"

# 3. Re-correr (procesa solo la borrada, las demás se saltan por idempotencia)
python conciliador.py
```

### 3.2 Reprocesar VARIAS facturas

```bash
GASOLINA="/c/Users/franc/Mi unidad/Inteligencia Artificial/Productividad/Gasolina"

for fc in 74783 74820 74864; do
    rm -rf "$GASOLINA/Facturas/FC$fc"
done

rm -f "$GASOLINA/Control/~\$Control_Conciliacion_Combustibles.xlsx"
python conciliador.py
```

### 3.3 Reprocesar TODO desde cero

```bash
GASOLINA="/c/Users/franc/Mi unidad/Inteligencia Artificial/Productividad/Gasolina"

# Snapshot defensivo OBLIGATORIO antes de borrar todo
SNAPSHOT="$GASOLINA/_snapshots/$(date +%Y%m%d_%H%M)_full_reprocess"
mkdir -p "$SNAPSHOT"
cp -r "$GASOLINA/Facturas" "$SNAPSHOT/"
cp "$GASOLINA/Control/Control_Conciliacion_Combustibles.xlsx" "$SNAPSHOT/"

# Borrar
rm -rf "$GASOLINA/Facturas"
mkdir "$GASOLINA/Facturas"
rm "$GASOLINA/Control/Control_Conciliacion_Combustibles.xlsx"

# Re-correr
python conciliador.py
```

### 3.4 Cambiar año / período sin tocar `.env`

```bash
python conciliador.py --since 2025-01-01 --until 2025-12-31
```

Sobrescribe `DATE_FROM`/`DATE_TO` solo para esa corrida.

### 3.5 Restaurar desde un snapshot

```bash
GASOLINA="/c/Users/franc/Mi unidad/Inteligencia Artificial/Productividad/Gasolina"

# Listar snapshots disponibles
ls "$GASOLINA/_snapshots/"

# Restaurar uno (cambia la fecha)
SNAPSHOT="$GASOLINA/_snapshots/20260427_0604_pre_lote"
rm -rf "$GASOLINA/Facturas"
cp -r "$SNAPSHOT/Facturas" "$GASOLINA/Facturas"
cp "$SNAPSHOT/Control_Conciliacion_Combustibles.xlsx" "$GASOLINA/Control/"
```

---

## 4. Generar informe (DESPUÉS de validar)

> ⚠️ Solo generar el informe **después** de completar los pasos 1-3 anteriores.
> Si lo generas antes de validar, las cifras de "Pendiente revisión manual" o "diferencia" pueden ser ruido (errores de Vision) en lugar de hallazgos reales.

### 4.1 Reunir los datos del Excel

Abrir `Control_Conciliacion_Combustibles.xlsx` y filtrar la hoja **Conciliación** por col K:

- Filtrar por **`No hay remisión`** → copia las filas (NUMDOCTRA, Fecha, Valor) → estos son los faltantes a reclamar
- Filtrar por **`Remisión con valor diferente`** → copia las filas (NUMDOCTRA, Bote, Fecha, V. factura, V. remisión, Diferencia) → estos son los hallazgos a discutir

Mira también la hoja **Resumen** para totales.

### 4.2 Plantilla de email a Nautiturismo

Adaptar según los datos del periodo:

```
Asunto: Solicitud de revisión – Facturación combustible <PERIODO>

Estimados [Nombre de contacto / Equipo de Cartera de Nautiturismo SAS]:

En el marco del proceso de conciliación de las facturas de combustible
recibidas durante el periodo <PERIODO>, encontramos las siguientes
situaciones que requieren su revisión.

1) FACTURAS SIN REMISIÓN ADJUNTA (N facturas — $XXX.XXX)

Las siguientes facturas llegaron vía Facture (no-responder@facture.co)
sin la remisión correspondiente como anexo. Solicitamos comedidamente
el envío de las remisiones para soportar el despacho:

| NUMDOCTRA | Fecha factura | Valor facturado |
|-----------|---------------|-----------------|
| FCXXXXX   | DD/MM/AAAA    | $XXX.XXX        |
| ...       | ...           | ...             |
| TOTAL                     | $X.XXX.XXX      |

2) DIFERENCIAS DETECTADAS (N facturas)

Comparando los valores facturados contra el despacho registrado en
las remisiones, encontramos las siguientes inconsistencias:

| NUMDOCTRA | Bote | Fecha     | V. factura | V. remisión | Diferencia | A favor de |
|-----------|------|-----------|-----------:|------------:|-----------:|------------|
| FCXXXXX   | BXX  | DD/MM/AA  | $X.XXX.XXX |  $X.XXX.XXX | +$XXX.XXX  | Nautiturismo / Todomar |
| ...       | ...  | ...       | ...        | ...         | ...        | ...        |
|-----------|------|-----------|-----------:|------------:|-----------:|------------|
| Subtotal a favor de Todomar:                                   | $XXX.XXX |
| Subtotal a favor de Nautiturismo:                              | $XXX.XXX |
| Neto:                                                          | $XXX.XXX |

Solicitamos su revisión y, en caso de confirmar las inconsistencias,
la emisión de la nota crédito correspondiente, así como el envío de
las N remisiones faltantes mencionadas en el numeral 1.

Quedamos atentos a su pronta respuesta para cerrar el periodo.

Cordialmente,

Francisco Cortázar
Todomar CHL S.A.S.
NIT 806.003.144
[teléfono]
[correo]
```

### 4.3 Anexos sugeridos

Si Nautiturismo necesita evidencia, puedes adjuntar:

- Los PDFs de las facturas/remisiones mencionadas (están en `G:\...\Facturas\FC<num>\`)
- Una copia del `Control_Conciliacion_Combustibles.xlsx` (filtrada por las filas mencionadas)

---

## 5. Casos especiales y troubleshooting

### 5.1 "No hay remisión" (estado 🟡)

**Causa**: el ZIP del correo no contenía PDF de remisión adentro.

**Verificación**: abrir Gmail, buscar `subject:FCXXXXX`, mirar adjuntos del correo. Si efectivamente solo trae el ZIP de la factura → reclamar a Nautiturismo. Si trae también un adjunto separado (no en el ZIP) → bug del script, reportar.

### 5.2 "Pendiente revisión manual" (estado 🟠)

**Causa**: Claude Vision no pudo leer la imagen, devolvió respuesta no parseable, o el PDF no se renderizó bien.

**Acción**: abrir la imagen manualmente con el hipervínculo de col N, leer el valor a ojo, y completar las cols I, G, H, K, L manualmente en el Excel.

Si pasa con muchas (>5%): puede ser regresión del parser → reportar.

### 5.3 "Remisión con valor diferente" (estado 🔴)

**Causa**: Vision leyó la remisión pero el valor no cuadra con la factura (más de $1.000 de diferencia).

**Verificación obligatoria**: abrir factura (col M) y remisión (col N) y comparar con la imagen. Determinar:
- ¿Vision leyó mal? → reprocesar (sección 3.1)
- ¿Es diferencia real? → incluir en el informe a Nautiturismo

### 5.4 `numdoctra_not_expected`

**Causa**: llegó un correo con un FC<num> que no está en las 114 (o N) filas del Excel maestro.

**Acción**: confirmar si esa factura debería estar en el alcance del Excel. Si sí → agregarla al Excel maestro y reprocesar. Si no → ignorar (queda el ZIP descargado en disco para auditoría).

### 5.5 OAuth: `access_denied` o token expirado

```bash
rm "$(pwd)/token.json"
python conciliador.py --dry-run --limit 1
```

Re-genera el token. Si pide consentimiento de nuevo en navegador, dáselo.

### 5.6 Vision: `vision_api_failed` con mensaje sobre billing

Saldo agotado en Anthropic Console. Recargar en https://console.anthropic.com/settings/billing.

### 5.7 Cambiar el modelo de Vision (Sonnet ↔ Haiku)

Editar `.env`:

```
ANTHROPIC_VISION_MODEL=claude-haiku-4-5-20251001    # más barato, menos preciso
# o
ANTHROPIC_VISION_MODEL=claude-sonnet-4-6            # default, mejor precisión
```

---

## 6. Costos y monitoreo

### 6.1 Costo estimado por modelo

| Modelo | Por imagen | 100 facturas | 1.500 facturas (1 año) |
|---|---:|---:|---:|
| Haiku 4.5 | ~$0.001 | $0.10 | $1.50 |
| Sonnet 4.6 (default) | ~$0.008 | $0.80 | $12.00 |

### 6.2 Monitorear consumo

https://console.anthropic.com/usage

### 6.3 Si Vision está caro o no quieres usarlo

En `.env`:
```
ANTHROPIC_API_KEY=
```

Las remisiones escaneadas quedarán como **🟠 Pendiente revisión manual** y completas a mano.

---

## 7. Logs

Cada corrida genera un log JSON línea por línea en:

```
G:\Mi unidad\...\Gasolina\Control\logs\run_YYYYMMDD_HHMMSS.jsonl
```

Para revisar el más reciente:

```bash
GASOLINA="/c/Users/franc/Mi unidad/Inteligencia Artificial/Productividad/Gasolina"
LOG=$(ls -t "$GASOLINA/Control/logs/"*.jsonl | head -1)
echo "Log: $LOG"
cat "$LOG" | grep -i "warn\|error" | head -20    # ver problemas
cat "$LOG" | grep "conciliated" | head            # ver primeras conciliaciones
cat "$LOG" | grep "done"                           # estadística final
```

Para compartir un log conmigo (Claude) cuando algo falla:

```bash
cp "$LOG" ~/Downloads/Laura_Test/conciliador/_debug_run_$(date +%Y%m%d_%H%M).jsonl
cd ~/Downloads/Laura_Test
git add conciliador/_debug_run_*.jsonl
git commit -m "debug: log de corrida"
git push
```

Después de revisar, eliminar el log del repo:

```bash
git rm conciliador/_debug_run_*.jsonl
git commit -m "cleanup: remove debug log"
git push
```

---

## 8. Convenciones del repo

- **Rama de trabajo**: `claude/fix-sheet-auth-xC9KQ`
- **Tag de versión funcional**: `v1.0-funcional` (commit `a3c62e1`)
- **Archivos sensibles** (NO subir al repo): `.env`, `credentials.json`, `token.json` — todos ya están en `.gitignore`
- **Logs y snapshots**: viven en `G:\...\Gasolina\` (Drive), no en el repo

---

## TODO / Mejoras futuras

- [ ] Flag `--informe` para autogenerar el email/PDF a partir del Excel
- [ ] Verificación cruzada del valor extraído del PDF vs `VALORTRA` del Excel maestro (auditoría defensiva)
- [ ] Validar el bote contra una tabla maestra (placa → bote)
- [ ] Detección de duplicados por NUMDOCTRA en Gmail (mismo NUMDOCTRA en 2 correos)
- [ ] Soporte para procesar múltiples años en una sola corrida (con un Excel maestro consolidado)
