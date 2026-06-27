# Conciliador de Combustible — Resumen del Proyecto

> Documento de referencia para entender qué hace el sistema, cómo está construido,
> y dónde son las áreas con potencial de mejora.
> Última actualización: 27 abril 2026.

---

## 1. Qué hace (en una frase)

Lee los correos electrónicos de facturas de combustible que llegan a Todomar desde
Nautiturismo, los procesa automáticamente, valida que el valor facturado coincida
con la remisión, y deja todo organizado en disco y en un Excel auditable.

## 2. El problema que resuelve

**Sin el sistema (manual):**
- Llegan 30-40 correos al mes con facturas de combustible
- Cada uno trae un ZIP, dentro otro ZIP, dentro un PDF + foto/escaneo de la remisión
- Alguien tenía que abrir cada correo, descargar el ZIP, descomprimir, abrir los
  PDFs, comparar valores manualmente, organizar carpetas
- Para encontrar discrepancias había que ir mirando uno por uno
- Volumen mensual: ~3-4 horas de trabajo administrativo
- Riesgo alto de no detectar diferencias o duplicados

**Con el sistema (automatizado):**
- 1 comando procesa todo el periodo
- 105 facturas en ~10 minutos
- Detecta diferencias automáticamente (8 OK, 5 con diferencia, 3 sin remisión en
  la última corrida real)
- Cuesta ~$1 USD por mes en Claude Vision API
- Tiempo manual: 15 minutos de validación visual

---

## 3. Cómo funciona (flujo end-to-end)

```
[1] FUENTE DE FACTURAS ESPERADAS
   ├─ Excel maestro DETALLE FACTURAS COMBUSTIBLES.xlsx (formato legacy)
   └─ PDF Zeus de estado de cuenta (nuevo formato — 1 por año)
              ↓
[2] LECTURA DE GMAIL (OAuth + Gmail API)
   ├─ Filtro: from:no-responder@facture.co + subject:"TODOMAR CHL"
   ├─ Rango de fechas configurable
   └─ Solo correos con prefijo FC<num> en asunto (ignora FU, FR, etc.)
              ↓
[3] DESCARGA DE ZIP ADJUNTO
              ↓
[4] DESCOMPRESIÓN RECURSIVA (ZIP dentro de ZIP)
   ├─ Out: FAC-FC<num>.pdf (factura digital, con CUFE)
   ├─ Out: REM-FC<num>.pdf (remisión, foto escaneada)
   └─ Out: ad...xml (XML legal de la factura)
              ↓
[5] ORGANIZACIÓN EN DISCO
   G:\Mi unidad\...\Gasolina\Facturas\FC<num>\
   ├─ FAC-FC<num>.pdf
   └─ REM-FC<num>.pdf (o REM-FC<num>_1.pdf, _2.pdf si hay varias)
              ↓
[6] CLASIFICACIÓN DE PDFs
   ├─ Detecta factura por marcadores: CUFE, DIAN, FACTURA ELECTRÓNICA
   └─ Resto = remisiones
              ↓
[7] VALIDACIÓN DEFENSIVA DEL EMISOR
   ├─ Si NIT del PDF de factura ≠ 901459048 (Nautiturismo)
   └─ → mueve carpeta a G:\...\No_Aplica\ y loggea
              ↓
[8] EXTRACCIÓN DE VALORES (cascada)
   ├─ a) pdfplumber + regex (TOTAL, VALOR TOTAL) — gratis
   ├─ b) Claude Vision (Sonnet 4.6) — fallback para PDFs escaneados
   │       ├─ Renderiza PDF a PNG (scale 3.0)
   │       ├─ Manda a API con prompt JSON estructurado
   │       └─ Retry exponencial 4 intentos (rate limit, 5xx)
   └─ c) Si todo falla → "Pendiente revisión manual"
              ↓
[9] CONCILIACIÓN
   ├─ 0 remisiones → "No hay remisión"
   ├─ Pdfs OK + |fact - rem| ≤ $1.000 → "OK"
   ├─ Pdfs OK + |fact - rem| > $1.000 → "Remisión con valor diferente"
   ├─ Pdfs no legibles → "Pendiente revisión manual"
              ↓
[10] ESCRITURA AL EXCEL DE CONTROL
   Control_Conciliacion_Combustibles.xlsx con 3 hojas:
   ├─ Conciliación (114+ filas con cols A-O)
   ├─ Resumen (KPIs en vivo con fórmulas)
   └─ Log (1 fila por corrida)
              ↓
[11] HIPERVÍNCULOS CLICABLES EN COLS M Y N
   ├─ M: click → abre la factura PDF
   └─ N: click → abre la remisión PDF (o carpeta si hay varias)
              ↓
[12] ETIQUETADO EN GMAIL
   Aplica label "Procesado/Nautiturismo" al correo
   (idempotencia y trazabilidad)
              ↓
[13] LOG ESTRUCTURADO JSONL
   G:\...\Control\logs\run_<timestamp>.jsonl
   (auditable, una línea por evento)
```

---

## 4. Componentes principales

### 4.1 Autenticación (Gmail OAuth 2.0)
- **Tipo**: OAuth Desktop, proyecto `conciliador-combustible` en Google Cloud Console
- **Scope**: `gmail.modify` (leer correos + aplicar etiquetas)
- **Credenciales**: `credentials.json` local (gitignored)
- **Token**: `token.json` local generado en 1ª corrida, refresh automático
- **Por qué OAuth y no App Password**: el usuario tiene Google Workspace con políticas que pueden bloquear App Passwords

### 4.2 Filtrado y descarga de correos
- **Gmail API** con paginación (`messages.list` + `messages.get format=raw`)
- Filtro server-side por remitente, asunto, fecha
- Filtro client-side por regex `FC(\d+)` para descartar FU/FR/otros
- **Idempotencia doble**: existencia de `FAC-FC<num>.pdf` en disco + etiqueta Gmail

### 4.3 Manejo de ZIP anidados
- **`unzip_to`** con cola iterativa (no recursión)
- Detecta `.zip` dentro de ZIPs y los procesa también
- No escribe los ZIP intermedios a disco

### 4.4 Extracción de datos de PDFs (cascada de 3 niveles)
- **Nivel 1**: `pdfplumber.extract_text()` + regex
  - Funciona para facturas digitales con texto seleccionable (siempre cubre la factura DIAN)
- **Nivel 2**: Claude Vision API (Sonnet 4.6)
  - Renderiza PDF→PNG con `pypdfium2` a 3x escala
  - Prompt estructurado pide JSON con valor, bote, fecha
  - Cuesta ~$0.008 por imagen
  - Retry exponencial para errores transitorios
- **Nivel 3**: marca como "Pendiente revisión manual"
  - El usuario abre la imagen y completa a mano

### 4.5 Lógica de conciliación
- Tolerancia configurable (default $1.000)
- 4 estados terminales: OK / No hay remisión / Remisión con valor diferente / Pendiente revisión manual
- Convención de signo (positivo = a favor Nautiturismo, negativo = a favor Todomar)

### 4.6 Output: archivo Excel + logs
- **Excel** con formato profesional: zebra, bordes, header azul, hipervínculos azules, formato condicional por color de celda, hoja Resumen con KPI cards
- **JSONL log** estructurado, una línea por evento
- **Snapshots**: el usuario puede hacer copias defensivas antes de cada lote grande

---

## 5. Archivos del proyecto

```
conciliador/
├── conciliador.py          # Script principal (1300+ líneas)
├── COWORK_1_0.md           # Spec original (era para Cowork antes del refactor a Python)
├── README.md               # Setup inicial y uso básico
├── MANUAL.md               # Guía operacional (procesar período, validar, informe)
├── PROJECT_OVERVIEW.md     # Este documento
├── .env.example            # Plantilla de configuración
├── requirements.txt        # Dependencias Python
├── .env                    # (local, gitignored) credenciales reales
├── credentials.json        # (local, gitignored) OAuth Desktop de Google Cloud
└── token.json              # (local, gitignored) generado en 1ª corrida OAuth
```

---

## 6. Tecnologías usadas

| Categoría | Tecnología | Para qué |
|---|---|---|
| Lenguaje | Python 3.14 | Backend |
| Auth | Google OAuth 2.0 (Desktop) | Acceso a Gmail |
| Email | Gmail API (google-api-python-client) | Lectura de correos, etiquetado |
| PDF (texto) | pdfplumber | Extracción de texto de facturas digitales |
| PDF (render) | pypdfium2 | PDF → PNG para Vision API |
| Vision OCR | Anthropic Claude Vision (Sonnet 4.6) | Lectura de remisiones escaneadas |
| Excel | openpyxl | Generación de archivo de control con formato |
| Config | python-dotenv | Variables de entorno |
| Storage | Google Drive for Desktop | Archivos sincronizados a la nube via mount C:\ |
| VCS | Git + GitHub | Versionado |

---

## 7. Estado actual

### Lo que está funcionando
- ✅ OAuth + Gmail completamente operacional
- ✅ Descarga ZIP + descompresión recursiva
- ✅ Naming convention FAC-FC / REM-FC
- ✅ Clasificación factura/remisión por contenido
- ✅ Vision API con retry exponencial
- ✅ Conciliación con 4 estados
- ✅ Excel con zebra, hipervínculos clicables, KPIs, formato condicional
- ✅ Soporte para fuente xlsx o PDF Zeus (nuevo)
- ✅ Modo `--validate-source` para probar parser sin Gmail

### Última corrida real validada
- **Periodo**: ene-abr 2026
- **Correos en Gmail**: 157
- **No-FC filtrados**: 39
- **Procesados**: 105 (10 ya estaban + 3 fuera del Excel)
- **OK**: 91 (87% éxito de primer intento)
- **Diferencias detectadas**: 5 (verificadas como reales o como errores Vision)
- **Sin remisión**: 3 (a reclamar a Nautiturismo)
- **Pendientes Vision falló parseo JSON**: 6 (arreglado con parser robusto en commit 566eb39)
- **Costo Vision**: ~$0.80 USD para los 105

### Lo que está commiteado en `claude/fix-sheet-auth-xC9KQ`

Commits relevantes:
- `fd65ed3` — Spec original Cowork
- `b70028f` — Implementación Python inicial
- `1a620b6` — Organización en carpeta `conciliador/`
- `31be853` — Switch a Gmail API + OAuth (en vez de IMAP+AppPassword)
- `58a817e` — Naming convention FAC-FC / REM-FC
- `94e23c6` — Filtro de FC-only (excluye FU, FR)
- `05f6aab` — Recursive ZIP extraction (clave para encontrar remisiones)
- `a3c62e1` — Mejoras visuales Excel (zebra, bordes, iconos, KPI cards)
- `ee6e6cf` — Vision fallback para remisiones escaneadas
- `9b8c41f` — Sonnet 4.6 + scale 3.0 + prompt mejorado
- `566eb39` — Parser JSON robusto (extrae JSON de respuestas con prosa)
- `b5198e4` — MANUAL.md operacional
- `35c21be` — PDF Zeus parser + multi-source + retry exponencial

**Tag**: `v1.0-funcional` apunta a `a3c62e1`

---

## 8. Decisiones de diseño relevantes

### Por qué Python en vez de Cowork
1 año de facturas tarda <30 min con Python local vs horas con Cowork + miles de
tokens. Cowork tampoco maneja ZIPs anidados ni regex complejos sin código.

### Por qué OAuth en vez de App Password
Cuenta corporativa en Google Workspace donde el admin puede bloquear App Passwords.
OAuth siempre funciona con permiso explícito del usuario.

### Por qué Sonnet en vez de Haiku para Vision
Haiku 4.5 confundió un dígito en una remisión (5→4) generando una falsa diferencia
de $100k. Sonnet 4.6 es 5-7x más preciso, costo 5x más alto pero sigue siendo
trivial ($1 vs $0.20 para un año completo). Mejor pagar la precisión.

### Por qué escribimos a Excel en G:\ y no usamos la API de Drive
Drive for Desktop hace el sync automático. Es más rápido (escritura local
instantánea + sync background), no consume tokens API, y es transparente.

### Por qué idempotencia por archivo en disco y no por Excel/etiqueta
La fuente de verdad más confiable es el sistema de archivos. Si el script
crasheó después de descargar pero antes de etiquetar, la siguiente corrida
ve el archivo y no re-descarga. La etiqueta Gmail es solo para visibilidad
humana, no para decisión de procesamiento.

---

## 9. Limitaciones conocidas

1. **Una sola página de PDF** se manda a Vision. Si una remisión tiene varias
   páginas, solo lee la primera (en práctica las remisiones son 1 página).

2. **Sin OCR offline (Tesseract)**. Si no hay API key de Claude Vision o falla,
   queda como "Pendiente revisión manual". Por costo bajo de Vision no lo
   priorizamos.

3. **Bootstrap del control desde fuente cero**. No hay forma de regenerar el
   Excel desde las carpetas existentes en disco (requiere reprocesar correos).
   Esto puede ser problema si el usuario borra accidentalmente el Excel.

4. **No detecta facturas duplicadas en Gmail** (mismo NUMDOCTRA en 2 correos).
   La idempotencia evita reprocesar pero no genera alerta.

5. **No valida cruzado el valor de la factura contra el VALORTRA esperado**
   (Paso 5 del spec). Auditoría defensiva que está en backlog.

6. **No autogenera informe** para mandar a Nautiturismo. El usuario copia/pega
   del Excel a un email manualmente. Backlog.

7. **No procesa correos en tiempo real**. Hay que correr el script manualmente
   o programar con Task Scheduler.

---

## 10. Backlog / Ideas de mejora

Priorizadas por impacto:

### Alta prioridad
- [ ] **`--informe`**: autogenera el email/PDF a Nautiturismo desde el Excel
- [ ] **`--watch`**: procesa solo correos sin etiqueta (más rápido para uso diario)
- [ ] **Resumen al final de consola**: línea por línea de lo que cambió en esta corrida
- [ ] **ALERTAS_PENDIENTES.txt**: archivo con casos urgentes (diff > $50k, sin remisión)
- [ ] **Verificación cruzada valor factura PDF vs VALORTRA esperado** (auditoría)

### Media prioridad
- [ ] **Detección de duplicados**: alerta si llega un NUMDOCTRA en 2 correos
- [ ] **Modo `--rebuild-control`**: reconstruye el Excel a partir de las carpetas
- [ ] **Alertas por email**: digest diario con casos abiertos
- [ ] **OCR offline (Tesseract)**: fallback si Vision API no está disponible
- [ ] **Soporte multi-página** en remisiones (PDFs con múltiples páginas)

### Baja prioridad / Largo plazo
- [ ] **Migración a hybrid Make.com + Cloud Function**: para tiempo real sin
      depender del PC del usuario
- [ ] **Webhooks de Gmail (Pub/Sub)**: procesar inmediatamente al recibir
- [ ] **Dashboard web**: para ver KPIs en vivo desde cualquier dispositivo
- [ ] **Conciliación tri-vía**: factura ↔ remisión ↔ estado de cuenta Zeus

### Mejoras menores
- [ ] Soporte para múltiples cuentas Gmail
- [ ] Plantilla de informe personalizable (Markdown/Jinja2)
- [ ] Tests unitarios (cubrir conciliate, parse_zeus, etc.)
- [ ] Exportar control a PDF (con un comando)

---

## 11. Quién hace qué (responsabilidades)

| Componente | Responsabilidad | Función / archivo |
|---|---|---|
| `load_config()` | Lee `.env`, valida vars requeridas | `conciliador.py:39` |
| `RunLog` | Log estructurado JSONL | `conciliador.py:79` |
| `get_gmail_service()` | OAuth + cliente Gmail | `conciliador.py:135` |
| `gmail_search()` | Búsqueda con filtros | `conciliador.py:185` |
| `extract_zip_attachment()` | Extrae ZIP del MIME | `conciliador.py:228` |
| `unzip_to()` | Descomprime recursivo | `conciliador.py:280` |
| `classify_pdfs()` | Factura vs remisión por contenido | `conciliador.py:323` |
| `rename_classified()` | A nomenclatura Cowork (FAC-FC / REM-FC) | `conciliador.py:346` |
| `extract_factura_data()` | Regex sobre PDF factura | `conciliador.py:418` |
| `extract_remision_data()` | Regex + Vision fallback | `conciliador.py:434` |
| `vision_extract_remision()` | Llamada a Claude Vision con retry | `conciliador.py:498` |
| `conciliate()` | Lógica de los 4 estados | `conciliador.py:611` |
| `parse_zeus_account_pdf()` | Parser nuevo del estado de cuenta | `conciliador.py:702` |
| `bootstrap_control()` | Crea Excel con 114 filas y formato | `conciliador.py:780` |
| `update_control_row()` | Actualiza 1 fila tras procesar 1 factura | `conciliador.py:907` |
| `_build_resumen_sheet()` | KPI cards con colores | `conciliador.py:858` |
| `process_one_email()` | Orquesta el pipeline por correo | `conciliador.py:1080` |
| `main()` | CLI + flujo principal | `conciliador.py:1240` |

---

## 12. Métricas para considerar al pensar mejoras

- **Tiempo por factura**: ~5-10s (mayormente Vision API)
- **Costo por factura**: ~$0.008 (Vision Sonnet) + 0 (todo lo demás)
- **Precisión Vision**: ~87% al primer intento, 100% con re-corrida ocasional
- **Tasa de "Pendiente revisión manual"** después del parser fix: <2%
- **Tasa de "Sin remisión"**: ~3% (lo manda Nautiturismo o no)
- **Tasa de "Con diferencia real"**: ~5% (las que toca reclamar)
- **Operaciones manuales por mes (con el sistema)**: 15 min de validar Excel + redactar email
- **Operaciones manuales por mes (sin el sistema)**: 3-4 horas
