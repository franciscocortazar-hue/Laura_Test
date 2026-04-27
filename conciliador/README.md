# Conciliador de combustible — Python

Implementación local del spec [`COWORK_1_0.md`](./COWORK_1_0.md). Procesa los correos de Nautiturismo desde Gmail (Gmail API + OAuth), organiza ZIPs por carpeta `FC<num>`, extrae valores de los PDFs, concilia y escribe `Control_Conciliacion_Combustibles.xlsx`.

**Por qué Python en vez de Cowork**: 1 año de facturas (~1.500 correos) tarda <30 min y no consume tokens.

---

## 1. Setup (una sola vez, ~10 min)

### 1.1 Conseguir `credentials.json` (OAuth Desktop)

Ya está hecho: el cliente OAuth `conciliador-cli` está creado en el proyecto `conciliador-combustible` de Google Cloud Console. Para descargar el JSON:

1. Abre https://console.cloud.google.com/apis/credentials (proyecto `conciliador-combustible`).
2. En **IDs de clientes de OAuth 2.0** → fila `conciliador-cli` → click en el ícono de descarga (📥).
3. Guarda el archivo como **`credentials.json`** dentro de la carpeta `conciliador/` del repo.

> ⚠️ El archivo `credentials.json` está en `.gitignore` — nunca lo subas al repo.

**Verifica que la Gmail API esté habilitada** en el proyecto:
- https://console.cloud.google.com/apis/library/gmail.googleapis.com → debe decir "Habilitada". Si no, click en **Habilitar**.

### 1.2 Instalar dependencias
En Git Bash, **entra a la carpeta `conciliador/`** del repo y crea el venv ahí:

```bash
cd ~/Downloads/Laura_Test/conciliador
python -m venv .venv
source .venv/Scripts/activate          # Git Bash en Windows
python -m pip install -r requirements.txt
```

> Todos los comandos siguientes (cp, python conciliador.py, etc.) se corren desde dentro de `conciliador/` con el venv activado.

> Si tu Python no es 3.14 y `pdfplumber` da problemas, prueba `pip install pdfplumber==0.11.4`.

### 1.3 Configurar `.env`
```bash
cp .env.example .env
vi .env        # o notepad .env
```
Edita `.env` y llena solo:
- `GMAIL_USER` → tu correo de Todomar (ej. `francisco.cortazar@boats4u.co`)

Las rutas y los demás filtros ya vienen con los valores correctos. Las rutas de `credentials.json` y `token.json` por defecto apuntan a la misma carpeta del script — no hace falta tocarlas si pusiste `credentials.json` ahí.

> ⚠️ El archivo `.env` está en `.gitignore` — nunca lo subas al repo.

### 1.4 Verificar el Excel fuente
Asegúrate de que el Excel original esté guardado en:
```
G:\Mi unidad\Inteligencia Artificial\Productividad\Gasolina\DETALLE FACTURAS COMBUSTIBLES ENERO A ABRIL 24-2026.xlsx
```
(Si tu archivo se llama distinto, ajusta `SOURCE_EXCEL` en `.env`.)

---

## 2. Primera corrida — autorización OAuth

La primera vez que corras el script:

1. Se abre tu navegador con la pantalla de consentimiento de Google.
2. Eliges la cuenta `francisco.cortazar@boats4u.co` (o la que tenga acceso a los correos).
3. Google te pide autorizar a la app `conciliador-cli` para "leer, redactar, enviar y eliminar permanentemente todos tus correos de Gmail" (scope `gmail.modify`).
4. Click **Permitir** → la pestaña dice "The authentication flow has completed" → ciérrala.
5. El script genera `token.json` localmente y continúa.

Si ves "Esta aplicación no se ha verificado" durante el flujo: es esperado para apps OAuth en modo Test. Click **Avanzado → Ir a conciliador-cli (no seguro)** → continúa. Solo aparece la primera vez.

**A partir de la segunda corrida**, el script reusa `token.json` y NO abre navegador.

---

## 3. Uso

### 3.1 Modo dry-run (no descarga, solo lista)
Útil para verificar que el filtro Gmail encuentra lo que esperas:
```bash
python conciliador.py --dry-run --limit 5
```
Muestra los 5 correos más antiguos del rango con su `NUMDOCTRA`.

### 3.2 Prueba real con 2 correos
```bash
python conciliador.py --limit 2
```
Procesa los 2 más antiguos. Crea el archivo de control si no existe (con las 114 filas pre-cargadas y solo 2 conciliadas).

### 3.3 Lote completo del rango configurado
```bash
python conciliador.py
```
Procesa todos los correos del `DATE_FROM`/`DATE_TO` definidos en `.env`. Es **idempotente** — si ya hay carpeta `FC<num>\factura.pdf`, salta.

### 3.4 Procesar un año diferente
```bash
python conciliador.py --since 2025-01-01 --until 2025-12-31
```

---

## 4. Salida

- **`G:\...\Facturas\FC<NUMDOCTRA>\factura.pdf` y `remision*.pdf`** — un folder por factura.
- **`G:\...\Control\Control_Conciliacion_Combustibles.xlsx`** — control con 3 hojas:
  - `Conciliación` (las 114 filas + cols G-O llenas a medida)
  - `Resumen` (KPIs en vivo)
  - `Log` (auditoría por corrida)
- **`G:\...\Control\logs\run_<YYYYMMDD_HHMMSS>.jsonl`** — log estructurado JSON línea por línea (auditable).
- **`G:\...\No_Aplica\FC<num>\`** — facturas de emisor distinto a Nautiturismo (red de seguridad).
- **Etiqueta Gmail `Procesado/Nautiturismo`** se aplica a cada correo procesado.

---

## 5. Cómo funciona la extracción de PDFs

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

## 6. Solución de problemas

| Síntoma | Causa probable | Fix |
|---|---|---|
| `ERROR: no se encontro credentials.json` | Falta el archivo en la carpeta del script | Descárgalo de Google Cloud Console (paso 1.1) y guárdalo como `conciliador/credentials.json` |
| Pantalla "Esta aplicación no se ha verificado" en el navegador | App OAuth en modo Test | Click **Avanzado → Ir a conciliador-cli (no seguro)** |
| `access_denied` al final del flujo OAuth | Tu cuenta no está como Test User en el proyecto | En Cloud Console → Auth Platform → Audiencia → agrega tu correo en "Test users" |
| `gmail_search_result count=0` | Filtros no matchean | Prueba `--dry-run --since 2026-01-01 --until 2026-04-30`, revisa `GMAIL_SUBJECT_FILTER` |
| `factura_value_not_extracted` | Regex no encontró el total | Comparte el PDF, ajustamos los patrones |
| `bad_zip` | ZIP corrupto / no es ZIP | Mira el correo manualmente |
| `numdoctra_not_expected` | Factura no está en las 114 filas | Esperado si llegó algo fuera del alcance del Excel fuente |
| Token expira / `invalid_grant` | El `refresh_token` se invalidó (revocaste permiso, etc.) | Borra `token.json` y vuelve a correr — repite el flujo de navegador |

---

## 7. Diferencias con el spec Cowork

El script implementa exactamente la lógica de `COWORK_1_0.md`. Diferencias menores:
- **NUMDOCTRA del asunto**: regex `FC(\d+)` (más robusto que split por `;`).
- **Sin Chrome ni OCR a 600dpi**: todo Gmail API + pdfplumber. ~100x más rápido.
- **Idempotencia**: por existencia de `factura.pdf` en la carpeta destino + etiqueta Gmail.
- **Auth**: Gmail API + OAuth 2.0 (no requiere App Password ni 2FA en la cuenta).
