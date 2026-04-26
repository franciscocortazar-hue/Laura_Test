# Conciliador de combustible — Python

Implementación local del spec [`COWORK_1_0.md`](./COWORK_1_0.md). Procesa los correos de Nautiturismo desde Gmail, organiza ZIPs por carpeta `FC<num>`, extrae valores de los PDFs, concilia y escribe `Control_Conciliacion_Combustibles.xlsx`.

**Por qué Python en vez de Cowork**: 1 año de facturas (~1.500 correos) tarda <30 min y no consume tokens.

---

## 1. Setup (una sola vez, ~10 min)

### 1.1 Habilitar 2FA y crear App Password en Gmail
1. Entra a tu cuenta Google → **Seguridad**.
2. Activa **Verificación en 2 pasos** si no la tienes.
3. Vuelve a Seguridad → busca **Contraseñas de aplicaciones**.
4. Crea una nueva app password (nombre: `Conciliador combustible`). Copia los 16 caracteres.

### 1.2 Instalar dependencias
En Git Bash, dentro de la carpeta donde está `conciliador.py`:

```bash
python -m venv .venv
source .venv/Scripts/activate          # Git Bash en Windows
python -m pip install -r requirements.txt
```

> Si tu Python no es 3.14 y `pdfplumber` da problemas, prueba `pip install pdfplumber==0.11.4`.

### 1.3 Configurar credenciales y rutas
```bash
cp .env.example .env
```
Edita `.env` y llena:
- `GMAIL_USER` → tu correo de Todomar
- `GMAIL_APP_PASSWORD` → los 16 caracteres del paso 1.1 (sin espacios)
- Las rutas `SOURCE_EXCEL`, `FACTURAS_DIR`, `CONTROL_DIR`, `NO_APLICA_DIR` ya vienen con los valores correctos.

> ⚠️ El archivo `.env` está en `.gitignore` — nunca lo subas al repo.

### 1.4 Verificar el Excel fuente
Asegúrate de que el Excel original esté guardado en:
```
G:\Mi unidad\Inteligencia Artificial\Productividad\Gasolina\DETALLE FACTURAS COMBUSTIBLES ENERO A ABRIL 24-2026.xlsx
```
(Si tu archivo se llama distinto, ajusta `SOURCE_EXCEL` en `.env`.)

---

## 2. Uso

### 2.1 Modo dry-run (no descarga, solo lista)
Útil para verificar que el filtro Gmail encuentra lo que esperas:
```bash
python conciliador.py --dry-run --limit 5
```
Muestra los 5 correos más antiguos del rango con su `NUMDOCTRA`.

### 2.2 Prueba real con 2 correos
```bash
python conciliador.py --limit 2
```
Procesa los 2 más antiguos. Crea el archivo de control si no existe (con las 114 filas pre-cargadas y solo 2 conciliadas).

### 2.3 Lote completo del rango configurado
```bash
python conciliador.py
```
Procesa todos los correos del `DATE_FROM`/`DATE_TO` definidos en `.env`. Es **idempotente** — si ya hay carpeta `FC<num>\factura.pdf`, salta.

### 2.4 Procesar un año diferente
```bash
python conciliador.py --since 2025-01-01 --until 2025-12-31
```

---

## 3. Salida

- **`G:\...\Facturas\FC<NUMDOCTRA>\factura.pdf` y `remision*.pdf`** — un folder por factura.
- **`G:\...\Control\Control_Conciliacion_Combustibles.xlsx`** — control con 3 hojas:
  - `Conciliación` (las 114 filas + cols G-O llenas a medida)
  - `Resumen` (KPIs en vivo)
  - `Log` (auditoría por corrida)
- **`G:\...\Control\logs\run_<YYYYMMDD_HHMMSS>.jsonl`** — log estructurado JSON línea por línea (auditable).
- **`G:\...\No_Aplica\FC<num>\`** — facturas de emisor distinto a Nautiturismo (red de seguridad).
- **Etiqueta Gmail `Procesado/Nautiturismo`** se aplica a cada correo procesado.

---

## 4. Cómo funciona la extracción de PDFs

| Campo | Estrategia |
|---|---|
| Valor factura | Regex sobre texto `pdfplumber` busca "TOTAL FACTURA", "VALOR TOTAL", etc. |
| NIT emisor | Regex `NIT[:\s]*` para validar Nautiturismo |
| Valor remisión | Mismo patrón "TOTAL" |
| Nombre bote | Regex sobre "BOTE", "EMBARCACIÓN", "NAVE" |
| Fecha tanqueo | Regex sobre formato fecha colombiano dd/mm/aaaa hh:mm |

**Si la extracción falla** (PDF escaneado, layout no estándar): el script lo loggea como `factura_value_not_extracted` con un sample del texto. La fila queda sin las cols G-O y la puedes revisar manualmente.

Para esos casos podemos:
1. Mejorar las regex (mostrame un sample del PDF problemático).
2. Agregar fallback a OCR local (`pytesseract`) o a la API de Claude Vision (~$0.001/PDF).

---

## 5. Solución de problemas

| Síntoma | Causa probable | Fix |
|---|---|---|
| `imaplib.error: ... AUTHENTICATIONFAILED` | App password incorrecta | Regenera el app password y revisa que no tenga espacios |
| `imap_search_result count=0` | Filtros no matchean | Prueba `--dry-run --since 2026-01-01 --until 2026-04-30`, revisa `GMAIL_SUBJECT_FILTER` |
| `factura_value_not_extracted` | Regex no encontró el total | Comparte el PDF, ajustamos los patrones |
| `bad_zip` | ZIP corrupto / no es ZIP | Mira el correo manualmente |
| `numdoctra_not_expected` | Factura no está en las 114 filas | Esperado si llegó algo fuera del alcance del Excel fuente |

---

## 6. Diferencias con el spec Cowork

El script implementa exactamente la lógica de `COWORK_1_0.md`. Diferencias menores:
- **NUMDOCTRA del asunto**: regex `FC(\d+)` (más robusto que split por `;`).
- **Sin Chrome ni OCR a 600dpi**: todo IMAP + pdfplumber. ~100x más rápido.
- **Idempotencia**: por existencia de `factura.pdf` en la carpeta destino + etiqueta Gmail.
