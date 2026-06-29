#!/usr/bin/env python3
"""
Conciliador de facturas de combustible Nautiturismo -> Todomar.

Implementacion Python del spec en COWORK_1_0.md.
Lee Gmail (Gmail API + OAuth), descarga ZIPs adjuntos, organiza por carpeta FC<NUM>,
extrae valores de los PDFs, concilia y escribe el archivo de control.
"""
from __future__ import annotations

import argparse
import base64
import email
import json
import os
import re
import shutil
from concurrent.futures import ThreadPoolExecutor, as_completed
import sys
import zipfile
from datetime import datetime, timezone
from email.header import decode_header
from email.utils import parsedate_to_datetime
from io import BytesIO
from pathlib import Path
from urllib.parse import quote

import pdfplumber
import pypdfium2 as pdfium
from dotenv import load_dotenv

try:
    import anthropic
    HAS_ANTHROPIC = True
except ImportError:
    HAS_ANTHROPIC = False
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from openpyxl import Workbook, load_workbook
from openpyxl.formatting.rule import CellIsRule, FormulaRule
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

GMAIL_SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]


# ============================================================
# Configuracion
# ============================================================

def load_config() -> dict:
    load_dotenv()

    def req(key: str) -> str:
        v = os.environ.get(key)
        if not v:
            sys.exit(f"ERROR: variable de entorno requerida no encontrada: {key}\n"
                     f"Crea un archivo .env basado en .env.example")
        return v

    here = Path(__file__).resolve().parent
    cfg = {
        "gmail_user": req("GMAIL_USER"),
        "credentials_path": Path(os.environ.get("GMAIL_CREDENTIALS_PATH", str(here / "credentials.json"))),
        "token_path": Path(os.environ.get("GMAIL_TOKEN_PATH", str(here / "token.json"))),
        "from_filter": os.environ.get("GMAIL_FROM_FILTER", "no-responder@facture.co"),
        "subject_filter": os.environ.get("GMAIL_SUBJECT_FILTER", "TODOMAR CHL"),
        "label_processed": os.environ.get("GMAIL_LABEL_PROCESSED", "Procesado/Nautiturismo"),
        "source_excel": Path(req("SOURCE_EXCEL")),
        "facturas_dir": Path(req("FACTURAS_DIR")),
        "control_dir": Path(req("CONTROL_DIR")),
        "no_aplica_dir": Path(req("NO_APLICA_DIR")),
        "control_filename": os.environ.get(
            "CONTROL_FILENAME", "Control_Conciliacion_Combustibles.xlsx"
        ),
        "nautiturismo_nit": os.environ.get("NAUTITURISMO_NIT", "901459048"),
        "tolerance_pesos": float(os.environ.get("TOLERANCE_PESOS", "1000")),
        "date_from": os.environ.get("DATE_FROM", "2026-01-01"),
        "date_to": os.environ.get("DATE_TO", "2026-04-30"),
        "anthropic_api_key": os.environ.get("ANTHROPIC_API_KEY"),
    }
    return cfg


# ============================================================
# Logging estructurado
# ============================================================

class RunLog:
    def __init__(self, control_dir: Path) -> None:
        self.events: list[dict] = []
        self.started_at = datetime.now(timezone.utc).isoformat()
        log_dir = control_dir / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.path = log_dir / f"run_{ts}.jsonl"

    def log(self, level: str, event: str, **fields) -> None:
        entry = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "level": level,
            "event": event,
            **fields,
        }
        self.events.append(entry)
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False, default=str) + "\n")
        prefix = {"info": "  ", "warn": "! ", "error": "X "}.get(level, "  ")
        print(f"{prefix}{event}: " + ", ".join(f"{k}={v}" for k, v in fields.items()))

    def info(self, event: str, **f) -> None: self.log("info", event, **f)
    def warn(self, event: str, **f) -> None: self.log("warn", event, **f)
    def error(self, event: str, **f) -> None: self.log("error", event, **f)


# ============================================================
# Parseo del asunto
# ============================================================

def extract_numdoctra(subject: str) -> str | None:
    m = re.search(r"FC(\d+)", subject or "")
    return m.group(1) if m else None


def decode_subject(raw: str) -> str:
    if not raw:
        return ""
    parts = decode_header(raw)
    out = []
    for text, enc in parts:
        if isinstance(text, bytes):
            try:
                out.append(text.decode(enc or "utf-8", errors="replace"))
            except LookupError:
                out.append(text.decode("utf-8", errors="replace"))
        else:
            out.append(text)
    return "".join(out)


# ============================================================
# Cliente Gmail API (OAuth)
# ============================================================

def get_gmail_service(cfg: dict, log: "RunLog"):
    """Devuelve un servicio Gmail API listo para usar.

    La primera vez abre el navegador para autorizar la app y guarda token.json.
    Las siguientes corridas reutilizan token.json (refrescando si expiro).
    """
    creds = None
    token_path = cfg["token_path"]
    creds_path = cfg["credentials_path"]

    if token_path.exists():
        creds = Credentials.from_authorized_user_file(str(token_path), GMAIL_SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            log.info("oauth_refresh_token")
            creds.refresh(Request())
        else:
            if not creds_path.exists():
                sys.exit(
                    f"ERROR: no se encontro credentials.json en {creds_path}\n"
                    f"Descargalo desde Google Cloud Console -> APIs & Services -> "
                    f"Credentials, y ponlo en esa ruta (o ajusta GMAIL_CREDENTIALS_PATH en .env)."
                )
            log.info("oauth_browser_flow_start", credentials=str(creds_path))
            flow = InstalledAppFlow.from_client_secrets_file(str(creds_path), GMAIL_SCOPES)
            creds = flow.run_local_server(port=0)
            log.info("oauth_browser_flow_done")
        token_path.parent.mkdir(parents=True, exist_ok=True)
        token_path.write_text(creds.to_json(), encoding="utf-8")
        log.info("oauth_token_saved", path=str(token_path))

    log.info("gmail_service_ready", user=cfg["gmail_user"])
    return build("gmail", "v1", credentials=creds, cache_discovery=False)


def gmail_search(service, cfg: dict, log: "RunLog") -> list[str]:
    """Busca mensajes que pasen el filtro y devuelve sus IDs."""
    since = datetime.strptime(cfg["date_from"], "%Y-%m-%d").strftime("%Y/%m/%d")
    # Gmail "before" es exclusivo; sumamos 1 dia para que sea inclusivo.
    until_dt = datetime.strptime(cfg["date_to"], "%Y-%m-%d")
    before = (until_dt.replace(day=until_dt.day) ).strftime("%Y/%m/%d")
    query = (
        f'from:{cfg["from_filter"]} '
        f'subject:"{cfg["subject_filter"]}" '
        f'after:{since} before:{before}'
    )
    log.info("gmail_search", query=query)

    ids: list[str] = []
    page_token = None
    while True:
        resp = service.users().messages().list(
            userId="me", q=query, pageToken=page_token, maxResults=500
        ).execute()
        for m in resp.get("messages", []):
            ids.append(m["id"])
        page_token = resp.get("nextPageToken")
        if not page_token:
            break
    log.info("gmail_search_result", count=len(ids))
    return ids


def fetch_message(service, msg_id: str) -> email.message.Message:
    raw_resp = service.users().messages().get(userId="me", id=msg_id, format="raw").execute()
    raw_bytes = base64.urlsafe_b64decode(raw_resp["raw"])
    return email.message_from_bytes(raw_bytes)


def message_date(msg: email.message.Message) -> datetime:
    raw = msg.get("Date", "")
    try:
        return parsedate_to_datetime(raw)
    except Exception:
        return datetime.now(timezone.utc)


def extract_zip_attachment(msg: email.message.Message) -> tuple[str, bytes] | None:
    for part in msg.walk():
        if part.get_content_maintype() == "multipart":
            continue
        filename = part.get_filename()
        if not filename:
            continue
        filename = decode_subject(filename)
        if filename.lower().endswith(".zip"):
            payload = part.get_payload(decode=True)
            if payload:
                return filename, payload
    return None


_LABEL_ID_CACHE: dict[str, str] = {}


def _get_or_create_label_id(service, label_name: str) -> str | None:
    if label_name in _LABEL_ID_CACHE:
        return _LABEL_ID_CACHE[label_name]
    try:
        existing = service.users().labels().list(userId="me").execute().get("labels", [])
        for lbl in existing:
            if lbl["name"] == label_name:
                _LABEL_ID_CACHE[label_name] = lbl["id"]
                return lbl["id"]
        created = service.users().labels().create(
            userId="me",
            body={
                "name": label_name,
                "labelListVisibility": "labelShow",
                "messageListVisibility": "show",
            },
        ).execute()
        _LABEL_ID_CACHE[label_name] = created["id"]
        return created["id"]
    except HttpError:
        return None


def add_label(service, msg_id: str, label_name: str) -> None:
    try:
        label_id = _get_or_create_label_id(service, label_name)
        if not label_id:
            return
        service.users().messages().modify(
            userId="me", id=msg_id, body={"addLabelIds": [label_id]}
        ).execute()
    except HttpError:
        pass


# ============================================================
# Manejo de PDFs
# ============================================================

def unzip_to(folder: Path, zip_bytes: bytes) -> list[Path]:
    """Extrae el ZIP en folder. Si encuentra ZIPs anidados, los descomprime recursivamente
    (Facture envia un ZIP que adentro trae otro ZIP con el PDF de la remision)."""
    folder.mkdir(parents=True, exist_ok=True)
    extracted: list[Path] = []
    pending: list[bytes] = [zip_bytes]
    while pending:
        current = pending.pop()
        try:
            with zipfile.ZipFile(BytesIO(current)) as z:
                for name in z.namelist():
                    if not name or name.endswith("/"):
                        continue
                    flat_name = Path(name).name
                    payload = z.read(name)
                    if flat_name.lower().endswith(".zip"):
                        # ZIP anidado: extraerlo recursivamente, no escribirlo a disco
                        pending.append(payload)
                    else:
                        target = folder / flat_name
                        target.write_bytes(payload)
                        extracted.append(target)
        except zipfile.BadZipFile:
            continue
    return extracted


def pdf_text(pdf_path: Path) -> str:
    try:
        with pdfplumber.open(str(pdf_path)) as pdf:
            return "\n".join((p.extract_text() or "") for p in pdf.pages)
    except Exception:
        return ""


def looks_like_factura(text: str) -> bool:
    t = (text or "").upper()
    markers = ["CUFE", "FACTURA ELECTR", "DIAN", "FACTURA DE VENTA"]
    return any(m in t for m in markers)


def looks_like_remision(text: str) -> bool:
    t = (text or "").upper()
    return "REMISI" in t or "DESPACHO" in t


def classify_pdfs(pdfs: list[Path]) -> tuple[Path | None, list[Path]]:
    factura: Path | None = None
    remisiones: list[Path] = []
    others: list[Path] = []
    for p in pdfs:
        txt = pdf_text(p)
        if looks_like_factura(txt) and factura is None:
            factura = p
        elif looks_like_remision(txt):
            remisiones.append(p)
        else:
            others.append(p)
    if factura is None and len(pdfs) == 1:
        factura = pdfs[0]
    elif factura is None and others:
        factura = others.pop(0)
    remisiones.extend(others)
    return factura, remisiones


def rename_classified(
    folder: Path, factura: Path | None, remisiones: list[Path], numdoctra: str
) -> tuple[Path | None, list[Path]]:
    new_factura = None
    if factura:
        new_factura = folder / f"FAC-FC{numdoctra}.pdf"
        if factura.resolve() != new_factura.resolve():
            shutil.move(str(factura), str(new_factura))
    new_remisiones: list[Path] = []
    if len(remisiones) == 1:
        target = folder / f"REM-FC{numdoctra}.pdf"
        if remisiones[0].resolve() != target.resolve():
            shutil.move(str(remisiones[0]), str(target))
        new_remisiones.append(target)
    else:
        for i, r in enumerate(remisiones, start=1):
            target = folder / f"REM-FC{numdoctra}_{i}.pdf"
            if r.resolve() != target.resolve():
                shutil.move(str(r), str(target))
            new_remisiones.append(target)
    return new_factura, new_remisiones


# ============================================================
# Extraccion de campos de los PDFs
# ============================================================

NUMBER_RE = re.compile(r"[\d][\d.,]*")

def parse_money(s: str) -> float | None:
    if s is None:
        return None
    s = s.strip().replace("$", "").replace(" ", "")
    if not s:
        return None
    has_dot = "." in s
    has_comma = "," in s
    if has_dot and has_comma:
        if s.rfind(".") > s.rfind(","):
            s = s.replace(",", "")
        else:
            s = s.replace(".", "").replace(",", ".")
    elif has_comma:
        if len(s.split(",")[-1]) <= 2:
            s = s.replace(",", ".")
        else:
            s = s.replace(",", "")
    elif has_dot:
        if s.count(".") > 1:
            s = s.replace(".", "")
        elif len(s.split(".")[-1]) == 3:
            s = s.replace(".", "")
    try:
        return float(s)
    except ValueError:
        return None


def find_money_after(text: str, keywords: list[str]) -> float | None:
    for kw in keywords:
        pat = re.compile(rf"{re.escape(kw)}[^\d\$]*\$?\s*([\d.,]+)", re.IGNORECASE)
        m = pat.search(text)
        if m:
            v = parse_money(m.group(1))
            if v is not None and v > 0:
                return v
    return None


def extract_factura_data(pdf_path: Path) -> dict:
    text = pdf_text(pdf_path)
    return {
        "valor": find_money_after(text, [
            "TOTAL FACTURA", "VALOR TOTAL", "TOTAL A PAGAR",
            "GRAN TOTAL", "TOTAL", "Total"
        ]),
        "nit_emisor": _find_nit(text),
        "n_remisiones_esperadas": _find_remisiones_count(text),
        "raw_text_sample": text[:200],
    }


def _find_remisiones_count(text: str) -> int | None:
    """Busca cuantas remisiones se mencionan en las observaciones de la factura.

    Patrones tipicos en facturas viejas que agrupan varios tanqueos:
      'OBSERVACIONES: 3 remisiones'
      'remisiones: 5'
      'Numero de remisiones: 2'
      'incluye 4 remisiones'
    Tambien acepta lista de numeros de remision separados por coma.
    """
    if not text:
        return None
    # Patron 1: numero seguido de 'remisi'
    m = re.search(r"(\d{1,3})\s*remisi", text, re.IGNORECASE)
    if m:
        return int(m.group(1))
    # Patron 2: 'remisiones' seguido de numero
    m = re.search(r"remisi[oó]n(?:es)?\s*[:\-=]?\s*(\d{1,3})", text, re.IGNORECASE)
    if m:
        return int(m.group(1))
    return None


def _find_nit(text: str) -> str | None:
    m = re.search(r"NIT[:\s]*([\d.\-]+)", text or "", re.IGNORECASE)
    if m:
        return re.sub(r"[.\-\s]", "", m.group(1))
    return None


def extract_remision_data(pdf_path: Path, api_key: str | None = None, log: "RunLog | None" = None) -> dict:
    """Extrae datos de una remision (puede contener varias remisiones internas).

    Retorna dict con estructura:
      {
        "file_name": "REM-FC74783.pdf",
        "remisiones": [
          {"valor": 685948, "bote": "B-10", "fecha_hora": "..."},
          ...
        ],
        "source": "regex" | "vision" | "empty",
      }

    Si pdfplumber no logra extraer el valor (PDF escaneado), cae a Claude
    Vision API si esta configurada. Vision puede detectar MULTIPLES remisiones
    en una sola imagen.
    """
    text = pdf_text(pdf_path)
    valor = find_money_after(text, ["TOTAL", "VALOR TOTAL", "Total"]) if text else None
    bote = _find_bote(text) if text else None
    fecha = _find_fecha_hora(text) if text else None

    if valor is not None:
        # Extraccion clasica funciono (1 remision por archivo, asume regex)
        return {
            "file_name": pdf_path.name,
            "remisiones": [{
                "remision_no": None,  # regex no extrae numero de remision
                "valor": valor,
                "bote": bote,
                "fecha_hora": fecha,
            }],
            "source": "regex",
        }

    # Sin valor extraido por regex -> intentar Vision si configurada
    if api_key and HAS_ANTHROPIC:
        if log is not None:
            log.info("vision_fallback", file=pdf_path.name)
        return vision_extract_remision(pdf_path, api_key, log)

    return {
        "file_name": pdf_path.name,
        "remisiones": [{
            "remision_no": None,
            "valor": None,
            "bote": bote,
            "fecha_hora": fecha,
        }],
        "source": "empty",
    }


VISION_PROMPT = """Esta es una imagen con UNA O MÁS remisiones (recibos POS) de una estación de
servicio de combustible para botes.

⚠️ IMPORTANTE: un solo archivo puede contener VARIAS remisiones (varios recibos
fotografiados juntos, o múltiples páginas). REVISA CUIDADOSAMENTE si hay más de
una remisión en la imagen. Cada recibo POS tiene su propio TOTAL, PLACA, FECHA.

Para CADA remisión que encuentres extrae:
- remision_no (número de la remisión, suele aparecer en la parte superior como "REMISION No. 1946", "REM No. 56201", "Orden de Venta: 68831". Ej: "1946")
- valor (TOTAL del despacho, número entero en pesos colombianos, sin $ ni puntos. Ej: 685940)
- bote (identificador del bote/embarcación, aparece como CLIENTE, PLACA, EMBARCACION, BOTE. Ej: "B-10", "Le Marie")
- fecha_hora (string formato YYYY-MM-DD HH:MM:SS. Ej: "2026-01-02 08:05:30")

⚠️ CUIDADO con el TOTAL — esto NO es el TOTAL:
- Números de **cédula (C.C.) o NIT** del cliente o de quien firma (suelen ser 7-10 dígitos: ej. "1.047.451.897")
- **Firmas** o números escritos a mano en el área de OBSERVACIONES
- **Número de remisión** (ej. "REMISION No. 1946")
- **Cantidad** de combustible (galones, ej. 42)
- **Precio unitario / VR.UNIDAD** (precio por galón, ej. 16.320)

El TOTAL es el resultado de cantidad × precio_unitario, suele aparecer en
el área del recibo etiquetada como "TOTAL" o como el monto principal en el
cuerpo. Para un tanqueo típico va de $50.000 a $2.000.000 pesos. Si vieras
un número de 9-10 dígitos (>$10M), probablemente es una cédula, NO el TOTAL.

REVISA CON CUIDADO los dígitos del TOTAL — algunos recibos tienen tinta clara o
resolución baja, verifica cada cifra antes de responder. Si no estás 100% seguro
de un campo, devuelve null para ese campo (es preferible null a un valor inventado
o un número que es otra cosa).

Responde SOLO con JSON válido, sin markdown, sin explicación:

{
  "remisiones": [
    {"remision_no": "1946", "valor": 685940, "bote": "Le Marie", "fecha_hora": "2026-02-15 00:00:00"},
    {"remision_no": "1947", "valor": 234567, "bote": "B-5", "fecha_hora": "2026-01-02 09:15:00"}
  ]
}

Si solo hay UNA remisión en la imagen, el array tendrá 1 elemento.
Si hay varias remisiones, una entrada por cada una.
Si remision_no no es visible, usa null para ese campo."""

# Si el valor extraido supera este threshold, loggea alerta (probable cedula u otro identificador)
VALOR_REMISION_SUSPICIOUS_THRESHOLD = 5_000_000  # $5M COP por remision es muy alto

# Fill rojo para resaltar filas con remisiones duplicadas
RED_DUPLICATE_FILL = PatternFill("solid", fgColor="FF9999")


def _add_duplicate_red_rule(ws, range_str: str, obs_col_letter: str, row_start: int = 2) -> None:
    """Agrega regla de formato condicional: pinta fila entera de rojo si la
    col Observaciones contiene 'duplicada' o 'ya usada' (deteccion de remisiones
    repetidas entre facturas).

    Idempotente: si ya existe una regla con esa formula, no la duplica.
    """
    existing_formulas = []
    try:
        for cf_range, rules in ws.conditional_formatting._cf_rules.items():
            for r in rules:
                if hasattr(r, "formula") and r.formula:
                    existing_formulas.extend(str(f) for f in r.formula)
    except Exception:
        pass

    for keyword in ("duplicada", "ya usada"):
        marker = f"SEARCH(\"{keyword}\""
        if any(marker in f for f in existing_formulas):
            continue
        formula = f'=ISNUMBER(SEARCH("{keyword}",${obs_col_letter}{row_start}))'
        ws.conditional_formatting.add(
            range_str,
            FormulaRule(formula=[formula], fill=RED_DUPLICATE_FILL, stopIfTrue=False),
        )


def render_pdf_first_page_to_png(pdf_path: Path, scale: float = 3.0) -> bytes:
    """Renderiza la primera pagina del PDF como PNG bytes."""
    pdf = pdfium.PdfDocument(str(pdf_path))
    try:
        page = pdf[0]
        pil_image = page.render(scale=scale).to_pil()
        buf = BytesIO()
        pil_image.save(buf, format="PNG")
        return buf.getvalue()
    finally:
        pdf.close()


def _empty_vision_result(pdf_path: Path, reason: str) -> dict:
    """Genera dict vacio compatible con el esquema esperado."""
    return {
        "file_name": pdf_path.name,
        "remisiones": [{
            "remision_no": None, "valor": None, "bote": None, "fecha_hora": None,
        }],
        "source": f"vision_failed:{reason}",
    }


def vision_extract_remision(pdf_path: Path, api_key: str, log: "RunLog | None" = None) -> dict:
    """Usa Claude Vision (Sonnet) para extraer datos de una imagen de remisiones.

    Retorna dict con clave 'remisiones' que es una lista de 1 o mas remisiones
    detectadas en la imagen (un solo archivo puede tener varios recibos POS).
    """
    if not HAS_ANTHROPIC:
        return _empty_vision_result(pdf_path, "anthropic_not_installed")
    try:
        png_bytes = render_pdf_first_page_to_png(pdf_path)
    except Exception as e:
        if log is not None:
            log.warn("pdf_render_failed", file=pdf_path.name, err=str(e))
        return _empty_vision_result(pdf_path, "pdf_render_failed")

    img_b64 = base64.b64encode(png_bytes).decode()
    # Timeout duro: 60s por llamada para evitar cuelgues indefinidos.
    # Configurable via env var ANTHROPIC_TIMEOUT (default 60).
    timeout_sec = float(os.environ.get("ANTHROPIC_TIMEOUT", "60"))
    client = anthropic.Anthropic(api_key=api_key, timeout=timeout_sec)
    # Cambio: default a Haiku 4.5 (5x mas rapido, ~10x mas barato).
    # Sonnet 4.6 sigue disponible via ANTHROPIC_VISION_MODEL=claude-sonnet-4-6
    model = os.environ.get("ANTHROPIC_VISION_MODEL", "claude-haiku-4-5-20251001")
    # Cambio: max retries 4 -> 2 para que un fallo no congele 30s+
    max_retries = int(os.environ.get("ANTHROPIC_MAX_RETRIES", "2"))

    def _call_vision():
        return client.messages.create(
            model=model,
            max_tokens=1024,  # mas tokens por si la imagen tiene varias remisiones
            messages=[{
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/png",
                            "data": img_b64,
                        },
                    },
                    {"type": "text", "text": VISION_PROMPT},
                ],
            }],
        )

    response_text = None
    last_err: Exception | None = None
    import time
    for attempt in range(max_retries):
        try:
            msg = _call_vision()
            response_text = msg.content[0].text.strip()
            break
        except Exception as e:
            last_err = e
            err_name = type(e).__name__
            err_msg = str(e)
            # Retry-able: rate limit, overloaded, connection issues, 5xx
            retryable = (
                "RateLimit" in err_name
                or "Overloaded" in err_name
                or "Connection" in err_name
                or "Timeout" in err_name
                or "APIStatusError" in err_name and ("529" in err_msg or "503" in err_msg or "502" in err_msg or "500" in err_msg)
            )
            if not retryable or attempt == max_retries - 1:
                if log is not None:
                    log.warn("vision_api_failed", file=pdf_path.name,
                             attempt=attempt + 1, err=f"{err_name}: {err_msg[:200]}")
                return _empty_vision_result(pdf_path, f"api_failed:{err_name}")
            wait = (2 ** attempt) * 2  # 2s, 4s, 8s, 16s
            if log is not None:
                log.warn("vision_retry", file=pdf_path.name,
                         attempt=attempt + 1, wait_sec=wait, err=err_name)
            time.sleep(wait)

    if response_text is None:
        return _empty_vision_result(pdf_path,
                                    f"api_failed:{type(last_err).__name__ if last_err else 'unknown'}")

    # Strip code fences si los hay
    if response_text.startswith("```"):
        lines = response_text.split("\n")
        end = len(lines)
        if lines and lines[-1].startswith("```"):
            end -= 1
        response_text = "\n".join(lines[1:end])

    # Si la respuesta tiene texto antes/despues del JSON, extraer solo el bloque {...}
    json_text = response_text.strip()
    if not json_text.startswith("{"):
        first_brace = json_text.find("{")
        last_brace = json_text.rfind("}")
        if first_brace >= 0 and last_brace > first_brace:
            json_text = json_text[first_brace:last_brace + 1]

    try:
        data = json.loads(json_text)
    except json.JSONDecodeError:
        if log is not None:
            log.warn("vision_response_not_json", file=pdf_path.name,
                     response=response_text[:500])
        return _empty_vision_result(pdf_path, "not_json")

    # Esquema esperado: {"remisiones": [{...}, {...}]}
    # Backwards compat: si viene como {"valor": ..., "bote": ..., "fecha_hora": ...} (1 sola), wrappearlo
    if "remisiones" in data and isinstance(data["remisiones"], list):
        raw_remisiones = data["remisiones"]
    elif "valor" in data or "bote" in data or "fecha_hora" in data:
        # Esquema legacy de 1 remision suelta
        raw_remisiones = [data]
    else:
        if log is not None:
            log.warn("vision_unexpected_schema", file=pdf_path.name, keys=list(data.keys()))
        return _empty_vision_result(pdf_path, "unexpected_schema")

    remisiones = []
    for r in raw_remisiones:
        if not isinstance(r, dict):
            continue
        valor = r.get("valor")
        if valor is not None:
            try:
                valor = float(valor)
            except (TypeError, ValueError):
                valor = None
        rno = r.get("remision_no")
        if rno is not None:
            rno = str(rno).strip() or None
        remisiones.append({
            "remision_no": rno,
            "valor": valor,
            "bote": r.get("bote"),
            "fecha_hora": r.get("fecha_hora"),
        })

    if not remisiones:
        return _empty_vision_result(pdf_path, "no_remisiones_in_response")

    if log is not None and len(remisiones) > 1:
        log.info("multiple_remisiones_in_file",
                 file=pdf_path.name, count=len(remisiones))

    return {
        "file_name": pdf_path.name,
        "remisiones": remisiones,
        "source": "vision",
    }


def _find_bote(text: str) -> str | None:
    patterns = [
        r"BOTE[:\s]+([A-Z0-9\-\s]{1,30})",
        r"EMBARCACI[OÓ]N[:\s]+([A-Z0-9\-\s]{1,30})",
        r"NOMBRE\s*BOTE[:\s]+([A-Z0-9\-\s]{1,30})",
        r"NAVE[:\s]+([A-Z0-9\-\s]{1,30})",
    ]
    for pat in patterns:
        m = re.search(pat, text or "", re.IGNORECASE)
        if m:
            return m.group(1).strip().split("\n")[0].strip()
    return None


def _find_fecha_hora(text: str) -> str | None:
    m = re.search(
        r"(\d{1,2}[/\-]\d{1,2}[/\-]\d{2,4}(?:\s+\d{1,2}:\d{2}(?::\d{2})?)?)",
        text or ""
    )
    return m.group(1) if m else None


# ============================================================
# Logica de conciliacion
# ============================================================

def conciliate(valor_factura: float, remisiones_data: list[dict], tol: float) -> tuple[str, float | None]:
    """Aplica las reglas de conciliación del spec COWORK_1_0.md.

    Retorna (estado, diferencia). diferencia=None cuando no aplica (sin remision
    o pendiente revision manual). diferencia=0.0 cuando OK. Numero con signo
    cuando hay diferencia real.
    """
    n = len(remisiones_data)

    # Caso 1: No hay archivos de remision en disco
    if n == 0:
        return ("No hay remisión", None)

    valores_extraidos = [r.get("valor") for r in remisiones_data if r.get("valor") is not None]

    # Caso 2: Hay remisiones pero ninguna se pudo leer
    if not valores_extraidos:
        return ("Pendiente revisión manual (OCR no concluyente)", None)

    # Caso 3: N>=2 remisiones y al menos una no legible
    if len(valores_extraidos) < n:
        no_leidas = n - len(valores_extraidos)
        return (
            f"Pendiente revisión manual ({no_leidas} de {n} remisiones no legible)",
            None,
        )

    # Caso 4 y 5: Todas legibles, comparar
    suma = sum(valores_extraidos)
    diff = round(valor_factura - suma, 2)
    if abs(diff) <= tol:
        return ("OK", 0.0)
    if n >= 2:
        return (
            f"Remisión con valor diferente ({n} remisiones, no coincide con el valor facturado)",
            diff,
        )
    return ("Remisión con valor diferente", diff)


# ============================================================
# Archivo de control (Excel)
# ============================================================

CONTROL_HEADERS = [
    "NUMDOCTRA", "Fecha factura", "Razón social", "NIT", "Tipo doc",
    "Valor factura", "Nombre de Bote", "Fecha y hora de tanqueo",
    "Valor remisión", "# Remisiones", "Conciliación", "Valor (diferencia)",
    "Link factura", "Link remisión(es)", "Última actualización", "Observaciones",
]

# Hoja "Detalle Remisiones": una fila por remision individual encontrada
DETALLE_HEADERS = [
    "NUMDOCTRA Factura", "Remisión No.", "Bote", "Fecha tanqueo",
    "Valor remisión", "Archivo origen", "Observaciones",
]
DETALLE_COL = {h: i + 1 for i, h in enumerate(DETALLE_HEADERS)}
COL = {h: i + 1 for i, h in enumerate(CONTROL_HEADERS)}
MONEY_FMT = '"$"#,##0;[Red]-"$"#,##0'
HYPERLINK_FONT = Font(color="0563C1", underline="single")

# Estilos visuales del archivo de control
THIN_BORDER = Border(
    left=Side(style="thin", color="D0D0D0"),
    right=Side(style="thin", color="D0D0D0"),
    top=Side(style="thin", color="D0D0D0"),
    bottom=Side(style="thin", color="D0D0D0"),
)
ZEBRA_FILL = PatternFill("solid", fgColor="F5F7FA")  # gris muy claro

# Iconos para columna Conciliación (visual de un vistazo)
STATUS_ICONS = [
    ("OK", "🟢"),
    ("Pendiente revisión manual", "🟠"),
    ("Remisión con valor diferente", "🔴"),
    ("No hay remisión", "🟡"),
]


def format_status_with_icon(status: str | None) -> str | None:
    if not status:
        return status
    for prefix, icon in STATUS_ICONS:
        if status.startswith(prefix):
            return f"{icon} {status}"
    return status


def path_to_file_url(path: Path) -> str:
    """Convierte una ruta local a un URL file:// que Excel pueda abrir al hacer click."""
    s = str(path).replace("\\", "/")
    return "file:///" + quote(s, safe="/:")


def set_hyperlink_cell(cell, target_path: Path | None, display_text: str) -> None:
    """Escribe una celda como hipervinculo clicable en Excel."""
    if target_path is None:
        cell.value = None
        return
    cell.value = display_text
    cell.hyperlink = path_to_file_url(target_path)
    cell.font = HYPERLINK_FONT


def _load_rows_from_xlsx(source_excel: Path) -> list[tuple]:
    """Lee las filas esperadas del Excel maestro DETALLE FACTURAS.

    Retorna tuplas (numdoctra, fecha, razon_social, nit, tipo_doc, valor).
    """
    src = load_workbook(str(source_excel), data_only=True)
    src_ws = src["Hoja1"]
    rows: list[tuple] = []
    for r in range(2, src_ws.max_row + 1):
        numdoctra = src_ws.cell(row=r, column=6).value
        if numdoctra is None:
            continue
        rows.append((
            int(numdoctra) if isinstance(numdoctra, float) else numdoctra,
            src_ws.cell(row=r, column=7).value,
            src_ws.cell(row=r, column=4).value,
            int(src_ws.cell(row=r, column=3).value) if isinstance(src_ws.cell(row=r, column=3).value, float) else src_ws.cell(row=r, column=3).value,
            f'{src_ws.cell(row=r, column=5).value or ""}{src_ws.cell(row=r, column=10).value or ""}',
            src_ws.cell(row=r, column=9).value,
        ))
    return rows


# Regex para parsear filas FC del PDF Zeus de estado de cuenta.
# Formato observado:
#   FC  0000077623  2026/03/02  CR 0000077623 2026/03/04   558,600.00   0.00   ...
ZEUS_FC_LINE = re.compile(
    r"^FC\s+(\d{6,})\s+(\d{4}/\d{1,2}/\d{1,2})\s+.*?"
    r"([\d,]+\.\d{2})\s+0\.00",
    re.IGNORECASE,
)


def parse_zeus_account_pdf(pdf_path: Path) -> list[dict]:
    """Parsea un PDF de estado de cuenta Zeus y extrae las facturas FC.

    Retorna lista de dicts: {numdoctra, fecha (YYYY/MM/DD), valor (float)}.
    Solo las filas FC (facturas), ignora CR (notas credito) y otras.
    """
    entries: list[dict] = []
    seen: set[str] = set()
    with pdfplumber.open(str(pdf_path)) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            for raw_line in text.split("\n"):
                line = raw_line.strip()
                m = ZEUS_FC_LINE.match(line)
                if not m:
                    continue
                numdoctra = m.group(1).lstrip("0") or "0"
                if numdoctra in seen:
                    continue
                fecha = m.group(2)
                valor = float(m.group(3).replace(",", ""))
                seen.add(numdoctra)
                entries.append({
                    "numdoctra": numdoctra,
                    "fecha": fecha,
                    "valor": valor,
                })
    return entries


def _load_rows_from_pdfs(source: Path) -> list[tuple]:
    """Lee filas esperadas desde un PDF Zeus o un directorio con varios PDFs.

    Para los campos que el PDF no trae (Razon social, NIT, Tipo doc), usa
    constantes Nautiturismo (NIT 901459048).
    """
    pdfs: list[Path]
    if source.is_dir():
        pdfs = sorted(source.glob("*.pdf"))
    else:
        pdfs = [source]
    if not pdfs:
        raise FileNotFoundError(f"No se encontraron PDFs en {source}")
    seen: set[str] = set()
    rows: list[tuple] = []
    for pdf in pdfs:
        for entry in parse_zeus_account_pdf(pdf):
            if entry["numdoctra"] in seen:
                continue
            seen.add(entry["numdoctra"])
            rows.append((
                int(entry["numdoctra"]),
                entry["fecha"],
                "NAUTITURISMO SAS",
                901459048,
                "FC",
                entry["valor"],
            ))
    return rows


def load_expected_rows(source: Path) -> list[tuple]:
    """Detecta el formato del source y delega al loader apropiado."""
    if source.is_dir():
        return _load_rows_from_pdfs(source)
    suffix = source.suffix.lower()
    if suffix == ".pdf":
        return _load_rows_from_pdfs(source)
    if suffix in (".xlsx", ".xls"):
        return _load_rows_from_xlsx(source)
    raise ValueError(f"Formato de source no reconocido: {source}")


def bootstrap_control(control_path: Path, source: Path, log: RunLog) -> None:
    if control_path.exists():
        log.info("control_exists", path=str(control_path))
        return
    log.info("control_bootstrap", path=str(control_path), source=str(source))
    rows = load_expected_rows(source)
    log.info("source_loaded", rows=len(rows), source_type=("pdf" if source.is_dir() or source.suffix.lower() == ".pdf" else "xlsx"))
    wb = Workbook()
    ws = wb.active
    ws.title = "Conciliación"

    header_font = Font(bold=True, color="FFFFFF", size=11)
    header_fill = PatternFill("solid", fgColor="305496")
    for col_idx, name in enumerate(CONTROL_HEADERS, start=1):
        c = ws.cell(row=1, column=col_idx, value=name)
        c.font = header_font
        c.fill = header_fill
        c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        c.border = THIN_BORDER

    for r, row in enumerate(rows, start=2):
        ws.cell(row=r, column=1, value=row[0])
        ws.cell(row=r, column=2, value=row[1])
        ws.cell(row=r, column=3, value=row[2])
        ws.cell(row=r, column=4, value=row[3])
        ws.cell(row=r, column=5, value=row[4])
        ws.cell(row=r, column=6, value=row[5])

    last_row = len(rows) + 1

    # Zebra + bordes + alineación + alto de fila para todas las celdas de datos
    n_cols = len(CONTROL_HEADERS)
    ws.row_dimensions[1].height = 28
    for r in range(2, last_row + 1):
        ws.row_dimensions[r].height = 22
        is_even = (r % 2 == 0)
        for c_idx in range(1, n_cols + 1):
            cell = ws.cell(row=r, column=c_idx)
            cell.border = THIN_BORDER
            cell.alignment = Alignment(vertical="center")
            if is_even:
                cell.fill = ZEBRA_FILL

    # Formato moneda en F, I, L
    for col_letter in ("F", "I", "L"):
        for r in range(2, last_row + 1):
            ws[f"{col_letter}{r}"].number_format = MONEY_FMT

    ws.freeze_panes = "A2"
    ws.auto_filter.ref = f"A1:{get_column_letter(n_cols)}{last_row}"

    # Formato condicional col K (Conciliación) — usa SEARCH para que matchee con o sin icono
    green = PatternFill("solid", fgColor="C6EFCE")
    yellow = PatternFill("solid", fgColor="FFEB9C")
    red = PatternFill("solid", fgColor="FFC7CE")
    orange = PatternFill("solid", fgColor="FFD9A6")
    rng_k = f"K2:K{last_row}"
    ws.conditional_formatting.add(
        rng_k, FormulaRule(formula=['ISNUMBER(SEARCH("OK",K2))'], fill=green, stopIfTrue=True)
    )
    ws.conditional_formatting.add(
        rng_k, FormulaRule(formula=['ISNUMBER(SEARCH("Pendiente revisión manual",K2))'], fill=orange, stopIfTrue=True)
    )
    ws.conditional_formatting.add(
        rng_k, FormulaRule(formula=['ISNUMBER(SEARCH("Remisión con valor diferente",K2))'], fill=red, stopIfTrue=True)
    )
    ws.conditional_formatting.add(
        rng_k, FormulaRule(formula=['ISNUMBER(SEARCH("No hay remisión",K2))'], fill=yellow, stopIfTrue=True)
    )
    # Formato condicional col L (diferencia)
    rng_l = f"L2:L{last_row}"
    ws.conditional_formatting.add(
        rng_l, CellIsRule(operator="greaterThan", formula=["1000"], fill=red)
    )
    ws.conditional_formatting.add(
        rng_l, CellIsRule(operator="lessThan", formula=["-1000"], fill=orange)
    )

    widths = {"A": 12, "B": 13, "C": 22, "D": 14, "E": 8, "F": 16, "G": 18,
              "H": 22, "I": 16, "J": 8, "K": 42, "L": 16, "M": 28, "N": 32, "O": 20,
              "P": 50}
    for letter, w in widths.items():
        ws.column_dimensions[letter].width = w

    # Marcar en rojo filas con remisiones duplicadas (observaciones contiene 'duplicada' o 'ya usada')
    _add_duplicate_red_rule(ws, f"A2:P{last_row}", "P", row_start=2)

    _build_resumen_sheet(wb, last_row)
    _build_log_sheet(wb)
    _build_detalle_remisiones_sheet(wb)

    control_path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(str(control_path))
    log.info("control_created", rows=len(rows))


def _build_resumen_sheet(wb: Workbook, last_data_row: int) -> None:
    ws = wb.create_sheet("Resumen")
    rng_k = f"'Conciliación'!K2:K{last_data_row}"
    rng_l = f"'Conciliación'!L2:L{last_data_row}"
    rng_f = f"'Conciliación'!F2:F{last_data_row}"
    rng_i = f"'Conciliación'!I2:I{last_data_row}"

    # Estilos
    title_font = Font(bold=True, size=18, color="1F4E79")
    section_font = Font(bold=True, size=13, color="FFFFFF")
    section_fill = PatternFill("solid", fgColor="305496")
    label_font = Font(size=11, color="44546A")
    value_font = Font(bold=True, size=16, color="1F4E79")
    money_font = Font(bold=True, size=14, color="1F4E79")
    centered = Alignment(horizontal="center", vertical="center")
    left_aligned = Alignment(horizontal="left", vertical="center", indent=1)

    # Colores de tarjetas por estado
    fill_ok = PatternFill("solid", fgColor="E2F0D9")        # verde claro
    fill_yellow = PatternFill("solid", fgColor="FFF2CC")    # amarillo claro
    fill_red = PatternFill("solid", fgColor="FCE4E4")       # rojo claro
    fill_orange = PatternFill("solid", fgColor="FCE6C9")    # naranja claro
    fill_blue = PatternFill("solid", fgColor="DEEBF7")      # azul claro

    # Fila 1: titulo
    ws.merge_cells("A1:C1")
    ws["A1"] = "Resumen de Conciliación"
    ws["A1"].font = title_font
    ws["A1"].alignment = centered
    ws.row_dimensions[1].height = 32

    # Fila 3: seccion General
    ws.merge_cells("A3:C3")
    ws["A3"] = "GENERAL"
    ws["A3"].font = section_font
    ws["A3"].fill = section_fill
    ws["A3"].alignment = centered
    ws.row_dimensions[3].height = 22

    def kpi_card(start_row: int, label: str, formula: str, fmt: str | None,
                 fill: PatternFill, val_font: Font = value_font) -> None:
        """Pinta una tarjeta KPI: A=label (fila start_row), B=valor (fila start_row+1)."""
        ws.cell(row=start_row, column=1, value=label).font = label_font
        ws.cell(row=start_row, column=1).alignment = left_aligned
        ws.cell(row=start_row, column=1).fill = fill
        ws.cell(row=start_row, column=1).border = THIN_BORDER

        c = ws.cell(row=start_row, column=2, value=formula)
        c.font = val_font
        c.alignment = Alignment(horizontal="right", vertical="center", indent=1)
        c.fill = fill
        c.border = THIN_BORDER
        if fmt:
            c.number_format = fmt
        ws.row_dimensions[start_row].height = 26

    # Fila 4-5: KPIs generales
    kpi_card(4, "Total facturas en alcance",
             f"=COUNTA('Conciliación'!A2:A{last_data_row})", None, fill_blue)
    kpi_card(5, "Total facturado ($)",
             f"=SUM({rng_f})", MONEY_FMT, fill_blue, money_font)

    # Fila 7: seccion Conciliacion
    ws.merge_cells("A7:C7")
    ws["A7"] = "ESTADO DE CONCILIACIÓN"
    ws["A7"].font = section_font
    ws["A7"].fill = section_fill
    ws["A7"].alignment = centered
    ws.row_dimensions[7].height = 22

    # Fila 8-11: KPIs por estado
    kpi_card(8, "🟢 OK (cuadradas)",
             f'=COUNTIF({rng_k},"*OK*")', None, fill_ok)
    kpi_card(9, "🟡 Sin remisión",
             f'=COUNTIF({rng_k},"*No hay remisión*")', None, fill_yellow)
    kpi_card(10, "🔴 Con diferencia",
             f'=COUNTIF({rng_k},"*Remisión con valor diferente*")', None, fill_red)
    kpi_card(11, "🟠 Pendiente revisión manual",
             f'=COUNTIF({rng_k},"*Pendiente revisión manual*")', None, fill_orange)

    # Fila 13: seccion Diferencias
    ws.merge_cells("A13:C13")
    ws["A13"] = "DIFERENCIAS DE VALOR"
    ws["A13"].font = section_font
    ws["A13"].fill = section_fill
    ws["A13"].alignment = centered
    ws.row_dimensions[13].height = 22

    # Fila 14-16
    # Roles:
    #   Todomar = proveedor (vende combustible, EMITE las facturas)
    #   Nautiturismo = cliente/comprador (paga, dueño de los botes)
    # Convencion de signo:
    #   factura > remision (positivo) = Todomar cobro de mas
    #     -> saldo A FAVOR DE NAUTITURISMO (el comprador, le deben)
    #   factura < remision (negativo) = Todomar despacho de mas sin facturar
    #     -> saldo A FAVOR DE TODOMAR (el proveedor podria reclamar)
    kpi_card(14, "A favor de Nautiturismo (factura > remisión — Todomar cobró de más)",
             f'=SUMIF({rng_l},">0")', MONEY_FMT, fill_red, money_font)
    kpi_card(15, "A favor de Todomar (factura < remisión — despacharon de más sin facturar)",
             f'=SUMIF({rng_l},"<0")', MONEY_FMT, fill_orange, money_font)
    kpi_card(16, "Neto de diferencias",
             f"=SUM({rng_l})", MONEY_FMT, fill_blue, money_font)

    # Fila 18: seccion Cobertura
    ws.merge_cells("A18:C18")
    ws["A18"] = "COBERTURA"
    ws["A18"].font = section_font
    ws["A18"].fill = section_fill
    ws["A18"].alignment = centered
    ws.row_dimensions[18].height = 22

    # Fila 19-20
    kpi_card(19, "Facturas procesadas",
             f'=COUNTIFS({rng_k},"<>")', None, fill_blue)
    kpi_card(20, "Facturas pendientes (sin correo)",
             f'=COUNTBLANK({rng_k})', None, fill_yellow)

    # Fila 22: seccion VALOR FACTURADO POR ESTADO (con $ — clave para auditoria)
    ws.merge_cells("A22:C22")
    ws["A22"] = "VALOR FACTURADO POR ESTADO"
    ws["A22"].font = section_font
    ws["A22"].fill = section_fill
    ws["A22"].alignment = centered
    ws.row_dimensions[22].height = 22

    # Rango de col P (Observaciones) para detectar "No se encontró factura"
    rng_p = f"'Conciliación'!P2:P{last_data_row}"
    # Sumar valores por estado (matching el icono prefijado en col K)
    kpi_card(23, "🟢 OK (cuadradas) — Total facturado",
             f'=SUMIF({rng_k},"*OK*",{rng_f})', MONEY_FMT, fill_ok, money_font)
    kpi_card(24, "🟡 Sin remisión — Total facturado",
             f'=SUMIF({rng_k},"*No hay remisión*",{rng_f})', MONEY_FMT, fill_yellow, money_font)
    # 'Con diferencia' separado en 2 lineas segun a favor de quien queda el saldo
    # Positivo (factura > remision): Todomar cobro de mas, saldo a favor de NAUTITURISMO
    # Negativo (factura < remision): despacharon de mas, saldo a favor de TODOMAR
    kpi_card(25, "🔴 Con diferencia A FAVOR DE NAUTITURISMO — Total facturado (a reclamar a Todomar)",
             f'=SUMIFS({rng_f},{rng_k},"*Remisión con valor diferente*",{rng_l},">0")',
             MONEY_FMT, fill_red, money_font)
    kpi_card(26, "🔴 Con diferencia A FAVOR DE TODOMAR — Total facturado",
             f'=SUMIFS({rng_f},{rng_k},"*Remisión con valor diferente*",{rng_l},"<0")',
             MONEY_FMT, fill_orange, money_font)
    kpi_card(27, "🟠 Pendiente revisión manual — Total facturado",
             f'=SUMIF({rng_k},"*Pendiente revisión manual*",{rng_f})', MONEY_FMT, fill_orange, money_font)
    kpi_card(28, "📭 Sin correo recibido — Total facturado (sin evidencia de tanqueo)",
             f'=SUMIF({rng_p},"*No se encontró*",{rng_f})', MONEY_FMT, fill_red, money_font)

    # Fila 30: total acumulado de filas sin evidencia valida
    ws.merge_cells("A30:C30")
    ws["A30"] = "⚠ TOTAL EXPUESTO (sin evidencia válida de despacho)"
    ws["A30"].font = section_font
    ws["A30"].fill = section_fill
    ws["A30"].alignment = centered
    ws.row_dimensions[30].height = 22

    kpi_card(31, "Total facturado SIN remisión o evidencia válida",
             (f'=SUMIF({rng_k},"*No hay remisión*",{rng_f})'
              f'+SUMIF({rng_k},"*Pendiente revisión manual*",{rng_f})'
              f'+SUMIF({rng_p},"*No se encontró*",{rng_f})'),
             MONEY_FMT, fill_red, money_font)

    ws.column_dimensions["A"].width = 56  # mas ancho por las etiquetas mas largas
    ws.column_dimensions["B"].width = 22
    ws.column_dimensions["C"].width = 4
    ws.sheet_view.showGridLines = False


def _build_log_sheet(wb: Workbook) -> None:
    ws = wb.create_sheet("Log")
    headers = [
        "Timestamp", "Correos leídos", "ZIPs descargados", "Facturas nuevas",
        "Facturas saltadas", "Errores", "Inconsistencias factura↔Excel", "Detalle",
    ]
    for i, h in enumerate(headers, start=1):
        c = ws.cell(row=1, column=i, value=h)
        c.font = Font(bold=True)
    widths = [22, 14, 16, 16, 16, 10, 24, 60]
    for i, w in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(i)].width = w


def _build_detalle_remisiones_sheet(wb: Workbook) -> None:
    """Hoja 'Detalle Remisiones': una fila por cada remision individual.

    Permite ver TODAS las remisiones (incluso las que estan agrupadas en
    un mismo archivo) con su numero, bote, valor, y origen. Tambien
    detecta numeros de remision duplicados (mismo numero en 2 facturas).
    """
    ws = wb.create_sheet("Detalle Remisiones")
    header_font = Font(bold=True, color="FFFFFF", size=11)
    header_fill = PatternFill("solid", fgColor="305496")
    for i, h in enumerate(DETALLE_HEADERS, start=1):
        c = ws.cell(row=1, column=i, value=h)
        c.font = header_font
        c.fill = header_fill
        c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        c.border = THIN_BORDER
    ws.row_dimensions[1].height = 28
    widths = {"A": 16, "B": 14, "C": 18, "D": 22, "E": 18, "F": 32, "G": 50}
    for letter, w in widths.items():
        ws.column_dimensions[letter].width = w
    ws.freeze_panes = "A2"
    # Marcar en rojo fila completa si Observaciones (col G) menciona duplicada
    _add_duplicate_red_rule(ws, "A2:G10000", "G", row_start=2)


def _ensure_detalle_sheet(wb: Workbook) -> None:
    """Si el Excel fue creado antes de que existiera 'Detalle Remisiones', la agrega."""
    if "Detalle Remisiones" not in wb.sheetnames:
        _build_detalle_remisiones_sheet(wb)


def load_remision_no_index(control_path: Path) -> dict:
    """Carga del Excel un indice {remision_no: NUMDOCTRA_factura} para detectar
    duplicados cuando se procesen nuevas remisiones."""
    index: dict = {}
    if not control_path.exists():
        return index
    try:
        wb = load_workbook(str(control_path), data_only=True, read_only=True)
        if "Detalle Remisiones" not in wb.sheetnames:
            wb.close()
            return index
        ws = wb["Detalle Remisiones"]
        for row in ws.iter_rows(min_row=2, values_only=True):
            if not row or len(row) < 2:
                continue
            numdoctra = row[0]
            remision_no = row[1]
            if numdoctra is None or remision_no is None:
                continue
            key = str(remision_no).strip()
            if not key:
                continue
            index[key] = str(int(numdoctra) if isinstance(numdoctra, float) else numdoctra).strip()
        wb.close()
    except Exception:
        pass
    return index


def clear_detalle_rows_for_factura(control_path: Path, numdoctra: str) -> None:
    """Borra del Detalle todas las filas asociadas a una NUMDOCTRA (para
    reprocesar limpio)."""
    if not control_path.exists():
        return
    wb = load_workbook(str(control_path))
    if "Detalle Remisiones" not in wb.sheetnames:
        wb.close()
        return
    ws = wb["Detalle Remisiones"]
    target = str(numdoctra).strip()
    rows_to_delete = []
    for r in range(2, ws.max_row + 1):
        v = ws.cell(row=r, column=1).value
        if v is None:
            continue
        if str(int(v) if isinstance(v, float) else v).strip() == target:
            rows_to_delete.append(r)
    # Borrar de abajo hacia arriba para no perder indices
    for r in reversed(rows_to_delete):
        ws.delete_rows(r)
    wb.save(str(control_path))


def append_detalle_remisiones(
    control_path: Path,
    numdoctra: str,
    remisiones: list[dict],
    file_name_per_remision: list[str],
    remision_no_index: dict,
) -> list[str]:
    """Agrega filas al Detalle Remisiones para cada remision encontrada.

    Detecta duplicados: si una remision_no ya fue vista en otra factura, lo nota.
    Modifica remision_no_index agregando las nuevas.

    Retorna lista de mensajes de duplicado (vacia si no hubo).
    """
    wb = load_workbook(str(control_path))
    _ensure_detalle_sheet(wb)
    ws = wb["Detalle Remisiones"]
    next_row = ws.max_row + 1
    if next_row == 2 and ws.cell(row=2, column=1).value is None:
        next_row = 2

    duplicate_msgs: list[str] = []
    money_fmt = MONEY_FMT

    for r, file_name in zip(remisiones, file_name_per_remision):
        rno = r.get("remision_no")
        obs = ""
        if rno:
            rno_key = str(rno).strip()
            if rno_key in remision_no_index and remision_no_index[rno_key] != str(numdoctra).strip():
                msg = f"⚠ Remisión No. {rno_key} ya usada en factura FC{remision_no_index[rno_key]}"
                obs = msg
                duplicate_msgs.append(msg)
            else:
                remision_no_index[rno_key] = str(numdoctra).strip()

        ws.cell(row=next_row, column=DETALLE_COL["NUMDOCTRA Factura"], value=numdoctra)
        ws.cell(row=next_row, column=DETALLE_COL["Remisión No."], value=rno)
        ws.cell(row=next_row, column=DETALLE_COL["Bote"], value=r.get("bote"))
        ws.cell(row=next_row, column=DETALLE_COL["Fecha tanqueo"], value=r.get("fecha_hora"))
        c_val = ws.cell(row=next_row, column=DETALLE_COL["Valor remisión"], value=r.get("valor"))
        if r.get("valor") is not None:
            c_val.number_format = money_fmt
        ws.cell(row=next_row, column=DETALLE_COL["Archivo origen"], value=file_name)
        ws.cell(row=next_row, column=DETALLE_COL["Observaciones"], value=obs or None)

        next_row += 1

    wb.save(str(control_path))
    return duplicate_msgs


def detectar_duplicados_remisiones(control_path: Path, log: RunLog) -> int:
    """Escanea la hoja Detalle Remisiones completa y marca duplicados.

    Una remision esta duplicada si su numero aparece en mas de una NUMDOCTRA
    distinta. Marca todas las apariciones con la observacion correspondiente.

    Util si se cargo Detalle antes de tener la deteccion en tiempo real.
    Retorna cuantas filas se marcaron como duplicado.
    """
    wb = load_workbook(str(control_path))
    if "Detalle Remisiones" not in wb.sheetnames:
        log.warn("detalle_sheet_missing")
        return 0
    ws = wb["Detalle Remisiones"]

    # Indice: remision_no -> lista de (row, numdoctra)
    from collections import defaultdict
    by_rno: dict = defaultdict(list)
    for r in range(2, ws.max_row + 1):
        numdoctra = ws.cell(row=r, column=DETALLE_COL["NUMDOCTRA Factura"]).value
        rno = ws.cell(row=r, column=DETALLE_COL["Remisión No."]).value
        if numdoctra is None or rno is None:
            continue
        rno_key = str(rno).strip()
        num_str = str(int(numdoctra) if isinstance(numdoctra, float) else numdoctra).strip()
        by_rno[rno_key].append((r, num_str))

    marked = 0
    for rno, occurrences in by_rno.items():
        if len(occurrences) <= 1:
            continue
        unique_numdoctras = sorted(set(num for _, num in occurrences))
        if len(unique_numdoctras) <= 1:
            continue  # mismo NUMDOCTRA repetido no es duplicado (es reprocesamiento)
        # Hay duplicado real
        for row_num, my_numdoctra in occurrences:
            others = [n for n in unique_numdoctras if n != my_numdoctra]
            msg = f"⚠ Remisión No. {rno} duplicada en facturas: FC{', FC'.join(others)}"
            cell = ws.cell(row=row_num, column=DETALLE_COL["Observaciones"])
            existing = cell.value or ""
            if "duplicada" not in existing.lower():
                cell.value = (existing + " | " if existing else "") + msg
            marked += 1

    wb.save(str(control_path))
    log.info("detectar_duplicados_done", filas_marcadas=marked, numeros_duplicados=len(
        [k for k, v in by_rno.items() if len(set(n for _, n in v)) > 1]
    ))
    return marked


def find_row_by_numdoctra(ws, numdoctra: int | str) -> int | None:
    target = str(numdoctra).strip()
    for r in range(2, ws.max_row + 1):
        v = ws.cell(row=r, column=1).value
        if v is None:
            continue
        if str(int(v) if isinstance(v, float) else v).strip() == target:
            return r
    return None


def _ensure_observaciones_header(ws) -> None:
    """Si el Excel fue creado antes de que existiera col Observaciones, agrega
    el header para que las nuevas escrituras a esa col tengan etiqueta.
    Tambien asegura el formato condicional rojo para filas con duplicados."""
    col_idx = COL["Observaciones"]
    cell = ws.cell(row=1, column=col_idx)
    if cell.value != "Observaciones":
        cell.value = "Observaciones"
        cell.font = Font(bold=True, color="FFFFFF", size=11)
        cell.fill = PatternFill("solid", fgColor="305496")
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.border = THIN_BORDER
        ws.column_dimensions[get_column_letter(col_idx)].width = 50
    # Formato condicional: marcar en rojo fila con duplicada
    # (la helper detecta si ya existe y no duplica reglas)
    max_row = max(ws.max_row, 2)
    _add_duplicate_red_rule(ws, f"A2:P{max_row}", "P", row_start=2)


def update_control_row(
    control_path: Path,
    numdoctra: str,
    factura_data: dict,
    remisiones_data: list[dict],
    conciliacion: str,
    valor_diff: float | None,
    factura_link: Path | None,
    remision_links: list[Path],
    log: RunLog,
    observaciones: str | None = None,
) -> bool:
    wb = load_workbook(str(control_path))
    ws = wb["Conciliación"]
    _ensure_observaciones_header(ws)
    row = find_row_by_numdoctra(ws, numdoctra)
    if row is None:
        log.warn("numdoctra_not_in_control", numdoctra=numdoctra)
        wb.close()
        return False
    bote = ", ".join(filter(None, [r.get("bote") for r in remisiones_data])) or None
    fecha_h = next((r.get("fecha_hora") for r in remisiones_data if r.get("fecha_hora")), None)
    valores_extraidos = [r.get("valor") for r in remisiones_data if r.get("valor") is not None]
    suma_rem = sum(valores_extraidos) if valores_extraidos else None

    ws.cell(row=row, column=COL["Nombre de Bote"], value=bote)
    ws.cell(row=row, column=COL["Fecha y hora de tanqueo"], value=fecha_h)
    c_vr = ws.cell(row=row, column=COL["Valor remisión"], value=suma_rem)
    if suma_rem is not None:
        c_vr.number_format = MONEY_FMT
    ws.cell(row=row, column=COL["# Remisiones"], value=len(remisiones_data))
    ws.cell(row=row, column=COL["Conciliación"], value=format_status_with_icon(conciliacion))
    c_diff = ws.cell(row=row, column=COL["Valor (diferencia)"], value=valor_diff)
    if valor_diff is not None:
        c_diff.number_format = MONEY_FMT
    c_m = ws.cell(row=row, column=COL["Link factura"])
    set_hyperlink_cell(c_m, factura_link, factura_link.name if factura_link else "")

    c_n = ws.cell(row=row, column=COL["Link remisión(es)"])
    if not remision_links:
        c_n.value = None
    elif len(remision_links) == 1:
        set_hyperlink_cell(c_n, remision_links[0], remision_links[0].name)
    else:
        folder_path = remision_links[0].parent
        set_hyperlink_cell(c_n, folder_path, f"Carpeta ({len(remision_links)} remisiones)")

    ws.cell(row=row, column=COL["Última actualización"], value=datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    ws.cell(row=row, column=COL["Observaciones"], value=observaciones)

    wb.save(str(control_path))
    return True


def reprocesar_diferencias(control_path: Path, facturas_dir: Path, log: RunLog) -> tuple[int, int]:
    """Borra las carpetas FC<num> de facturas con conciliacion 'Remision con valor diferente'.

    No toca el Excel; cuando el usuario corra el script normal, la idempotencia
    detectara que la carpeta no existe y reprocesara esas facturas con el codigo
    actualizado (que detecta multiples remisiones por archivo y filtra cedulas).

    Retorna (carpetas_borradas, total_marcados_en_excel).
    """
    wb = load_workbook(str(control_path), data_only=True)
    ws = wb["Conciliación"]

    candidatos: list[str] = []
    for r in range(2, ws.max_row + 1):
        conc = ws.cell(row=r, column=COL["Conciliación"]).value
        if not conc:
            continue
        if "diferente" in str(conc).lower():
            numdoctra = ws.cell(row=r, column=COL["NUMDOCTRA"]).value
            if numdoctra is None:
                continue
            num_str = str(int(numdoctra) if isinstance(numdoctra, float) else numdoctra).strip()
            candidatos.append(num_str)

    deleted = 0
    for num in candidatos:
        folder = facturas_dir / f"FC{num}"
        if folder.exists():
            shutil.rmtree(folder)
            deleted += 1
            log.info("folder_deleted_for_reprocess", numdoctra=num, folder=str(folder))

    log.info("reprocesar_diferencias_done",
             marcados=len(candidatos), borrados=deleted)
    return deleted, len(candidatos)


def _parse_fecha_safe(value) -> datetime | None:
    """Intenta parsear una fecha en multiples formatos. Devuelve None si falla."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    s = str(value).strip()
    # Probar formato completo primero (sin truncar)
    for fmt in ("%Y/%m/%d %H:%M:%S", "%Y-%m-%d %H:%M:%S", "%d/%m/%Y %H:%M:%S",
                "%Y/%m/%d %H:%M", "%Y-%m-%d %H:%M",
                "%Y/%m/%d", "%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    # Fallback: tomar solo los primeros 10 chars (YYYY-MM-DD)
    if len(s) >= 10:
        for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%d/%m/%Y"):
            try:
                return datetime.strptime(s[:10], fmt)
            except ValueError:
                continue
    return None


def generar_informe_duplicados(control_path: Path, facturas_dir: Path, log: RunLog) -> None:
    """Informe FORENSE de remisiones duplicadas (mismo numero en 2+ facturas).

    Para cada caso de duplicacion:
    - Lista las facturas donde aparece la misma remision_no
    - Compara valor, bote, fecha — clasifica fuerza del caso
    - Filtra reuso de consecutivo por cambio de sistema (gap temporal > 12 meses)
    - Calcula monto duplicado a recuperar (solo casos validos)
    - Construye paths a los PDFs originales como evidencia documental

    Genera en la carpeta Control/:
      - informe_duplicados.csv (todas las apariciones, plano)
      - INFORME_DUPLICADOS.md (caso por caso, listo para sustentar reclamacion)
    """
    import csv
    from collections import defaultdict

    wb = load_workbook(str(control_path), data_only=True)
    if "Detalle Remisiones" not in wb.sheetnames:
        log.warn("detalle_sheet_missing")
        print("\n  ⚠ La hoja 'Detalle Remisiones' no existe en el Excel.")
        print("  Es porque las facturas fueron procesadas antes de implementar la funcionalidad.")
        print("  Reprocesa las facturas relevantes para tener el numero de remision extraido.")
        return

    ws = wb["Detalle Remisiones"]

    # Construir indice {numdoctra: fecha_factura} desde Conciliacion
    # Es mas confiable que fecha tanqueo (que viene de Vision) para detectar
    # cambios de sistema.
    cons_ws = wb["Conciliación"]
    fecha_factura_por_num: dict = {}
    for r in range(2, cons_ws.max_row + 1):
        v = cons_ws.cell(row=r, column=COL["NUMDOCTRA"]).value
        if v is None:
            continue
        f = cons_ws.cell(row=r, column=COL["Fecha factura"]).value
        num_str = str(int(v) if isinstance(v, float) else v).strip()
        fecha_factura_por_num[num_str] = f

    # Agrupar por remision_no
    by_rno: dict = defaultdict(list)
    for r in range(2, ws.max_row + 1):
        numdoctra = ws.cell(row=r, column=DETALLE_COL["NUMDOCTRA Factura"]).value
        rno = ws.cell(row=r, column=DETALLE_COL["Remisión No."]).value
        if numdoctra is None or rno is None:
            continue
        bote = ws.cell(row=r, column=DETALLE_COL["Bote"]).value
        fecha_tanqueo = ws.cell(row=r, column=DETALLE_COL["Fecha tanqueo"]).value
        valor = ws.cell(row=r, column=DETALLE_COL["Valor remisión"]).value
        archivo = ws.cell(row=r, column=DETALLE_COL["Archivo origen"]).value
        rno_key = str(rno).strip()
        num_str = str(int(numdoctra) if isinstance(numdoctra, float) else numdoctra).strip()
        by_rno[rno_key].append({
            "numdoctra": num_str, "bote": bote, "fecha_tanqueo": fecha_tanqueo,
            "fecha_factura": fecha_factura_por_num.get(num_str),
            "valor": valor, "archivo": archivo or "",
        })

    # Filtrar a duplicados reales (>=2 NUMDOCTRA distintos)
    duplicates: dict = {}
    for rno, occurrences in by_rno.items():
        unique_numdoctras = set(o["numdoctra"] for o in occurrences)
        if len(unique_numdoctras) >= 2:
            duplicates[rno] = occurrences

    # Umbral para "cambio de sistema": gap temporal entre apariciones > N dias
    # Default 365 dias (1 año); configurable via env CONCILIADOR_GAP_SISTEMA_DIAS
    gap_sistema_dias = int(os.environ.get("CONCILIADOR_GAP_SISTEMA_DIAS", "365"))

    out_dir = control_path.parent

    if not duplicates:
        print("\n" + "=" * 70)
        print("  ✅ NO se encontraron remisiones duplicadas.")
        print("=" * 70)
        log.info("informe_duplicados_sin_hallazgos")
        return

    # Clasificar cada caso por fuerza de evidencia
    cases = []
    for rno, occurrences in duplicates.items():
        valores = [o["valor"] for o in occurrences if isinstance(o["valor"], (int, float))]
        botes_norm = [str(o["bote"]).strip().upper() for o in occurrences if o["bote"]]

        valores_iguales = len(set(valores)) <= 1 and len(valores) >= 2
        botes_iguales = len(set(botes_norm)) <= 1 and len(botes_norm) >= 2

        # Calcular gap temporal entre las apariciones (usa fecha_factura primero,
        # cae a fecha_tanqueo si no esta)
        fechas_parsed = []
        for o in occurrences:
            f = _parse_fecha_safe(o.get("fecha_factura")) or _parse_fecha_safe(o.get("fecha_tanqueo"))
            if f:
                fechas_parsed.append(f)

        gap_dias = None
        if len(fechas_parsed) >= 2:
            gap_dias = (max(fechas_parsed) - min(fechas_parsed)).days

        # CASO ESPECIAL: cambio de sistema (gap > umbral)
        # = NO ES DUPLICADO REAL, es reuso de consecutivo
        if gap_dias is not None and gap_dias > gap_sistema_dias:
            evaluacion = (f"NO APLICA — Reuso de consecutivo por cambio de sistema "
                         f"(gap {gap_dias} días entre apariciones)")
            fuerza = "no_aplica"
            monto_duplicado = 0.0
        elif valores_iguales and botes_iguales:
            evaluacion = "COBRO DUPLICADO CONFIRMADO (mismo número, valor y bote)"
            fuerza = "alta"
            monto_duplicado = valores[0] * (len(occurrences) - 1) if valores else 0.0
        elif valores_iguales:
            evaluacion = "SOSPECHA FUERTE (mismo valor, diferente bote)"
            fuerza = "alta"
            monto_duplicado = valores[0] * (len(occurrences) - 1) if valores else 0.0
        elif botes_iguales:
            evaluacion = "SOSPECHA MEDIA (mismo bote, diferente valor)"
            fuerza = "media"
            monto_duplicado = 0.0
        else:
            evaluacion = "REQUIERE INVESTIGACIÓN (valores y botes distintos)"
            fuerza = "baja"
            monto_duplicado = 0.0

        cases.append({
            "rno": rno,
            "occurrences": occurrences,
            "evaluacion": evaluacion,
            "fuerza": fuerza,
            "monto_duplicado": monto_duplicado,
            "valores_iguales": valores_iguales,
            "botes_iguales": botes_iguales,
            "gap_dias": gap_dias,
        })

    # Ordenar por fuerza (alta primero) y luego por monto duplicado desc
    fuerza_order = {"alta": 0, "media": 1, "baja": 2, "no_aplica": 3}
    cases.sort(key=lambda c: (fuerza_order[c["fuerza"]], -c["monto_duplicado"]))

    # Totales
    total_apariciones = sum(len(c["occurrences"]) for c in cases)
    total_monto_duplicado = sum(c["monto_duplicado"] for c in cases)
    casos_confirmados = sum(1 for c in cases if c["fuerza"] == "alta")
    casos_sospechosos = sum(1 for c in cases if c["fuerza"] == "media")
    casos_investigar = sum(1 for c in cases if c["fuerza"] == "baja")
    casos_no_aplica = sum(1 for c in cases if c["fuerza"] == "no_aplica")

    # CSV plano (todas las apariciones)
    csv_path = out_dir / "informe_duplicados.csv"
    with csv_path.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["Remision_No", "Categoria", "NUMDOCTRA", "Fecha_factura",
                    "Fecha_tanqueo", "Bote", "Valor", "Archivo_origen",
                    "Path_factura", "Path_remision", "Evaluacion",
                    "Gap_dias", "Monto_duplicado_caso"])
        for case in cases:
            for occ in case["occurrences"]:
                path_factura = facturas_dir / f"FC{occ['numdoctra']}" / f"FAC-FC{occ['numdoctra']}.pdf"
                path_remision = facturas_dir / f"FC{occ['numdoctra']}" / occ["archivo"]
                w.writerow([
                    case["rno"], case["fuerza"], occ["numdoctra"],
                    occ["fecha_factura"] or "", occ["fecha_tanqueo"] or "",
                    occ["bote"] or "", occ["valor"] or "", occ["archivo"],
                    str(path_factura), str(path_remision),
                    case["evaluacion"], case["gap_dias"] or "",
                    case["monto_duplicado"],
                ])

    # MD forense
    md_path = out_dir / "INFORME_DUPLICADOS.md"
    L = []
    L.append("# Informe Forense — Remisiones Duplicadas")
    L.append("")
    L.append("**De:** Nautiturismo SAS (NIT 901.459.048)")
    L.append("**Para:** Todomar CHL S.A.S. (NIT 806.003.144)")
    L.append(f"**Fecha:** {datetime.now().strftime('%d/%m/%Y')}")
    L.append("")
    L.append("## Resumen ejecutivo")
    L.append("")
    L.append("Como parte del proceso de conciliación de facturas de combustible, identificamos")
    L.append(f"**{len(cases)} números de remisión que aparecen en más de una factura emitida por Todomar**.")
    L.append("")
    L.append("Cada caso fue evaluado con criterios objetivos (mismo valor, mismo bote, gap temporal")
    L.append(f"entre apariciones) para distinguir cobros duplicados reales de reusos de consecutivo")
    L.append(f"por cambio de sistema (gap > {gap_sistema_dias} días).")
    L.append("")
    L.append("| Métrica | Valor |")
    L.append("|---|---:|")
    L.append(f"| Números de remisión duplicados | **{len(cases)}** |")
    L.append(f"| Apariciones totales en facturas | {total_apariciones} |")
    L.append(f"| 🔴 Casos confirmados (mismo valor + bote) | {casos_confirmados} |")
    L.append(f"| 🟠 Casos con sospecha media | {casos_sospechosos} |")
    L.append(f"| 🟡 Casos por investigar | {casos_investigar} |")
    L.append(f"| ✅ Casos descartados (reuso por cambio de sistema) | {casos_no_aplica} |")
    L.append(f"| **Monto total facturado en duplicado (a recuperar)** | **${total_monto_duplicado:,.0f}** |")
    L.append("")
    L.append("**Criterios de clasificación:**")
    L.append(f"- ✅ **NO APLICA**: gap temporal entre apariciones > {gap_sistema_dias} días → reuso de consecutivo por cambio de sistema, NO es duplicado real")
    L.append("- 🔴 **ALTA — Confirmado**: mismo número + mismo valor + mismo bote (dentro del gap)")
    L.append("- 🟠 **MEDIA**: mismo número + mismo valor, bote diferente (verificar)")
    L.append("- 🟡 **BAJA**: mismo número pero valores o botes muy distintos (investigar manualmente)")
    L.append("")
    L.append("Para cada caso a continuación se presenta: las facturas afectadas, datos comparativos,")
    L.append("evaluación, y rutas a los PDFs originales como respaldo documental.")
    L.append("")
    L.append("---")
    L.append("")

    # Cada caso
    for idx, case in enumerate(cases, start=1):
        rno = case["rno"]
        occs = case["occurrences"]
        emoji = {"alta": "🔴", "media": "🟠", "baja": "🟡", "no_aplica": "✅"}[case["fuerza"]]

        L.append(f"## Caso {idx}: Remisión No. **{rno}** — aparece en {len(occs)} facturas {emoji}")
        L.append("")
        L.append(f"**Evaluación**: {case['evaluacion']}")
        if case["gap_dias"] is not None:
            anios = case["gap_dias"] / 365.25
            L.append(f"**Gap temporal entre apariciones**: {case['gap_dias']} días (~{anios:.1f} años)")
        if case["monto_duplicado"] > 0:
            L.append(f"**Monto duplicado (a recuperar)**: ${case['monto_duplicado']:,.0f}")
        L.append("")
        L.append("### Apariciones")
        L.append("")
        L.append("| # | NUMDOCTRA | Fecha factura | Fecha tanqueo | Bote | Valor | Archivo origen |")
        L.append("|---|---|---|---|---|---:|---|")
        for i, occ in enumerate(occs, start=1):
            valor_str = f"${occ['valor']:,.0f}" if isinstance(occ["valor"], (int, float)) else "—"
            fecha_fact_str = str(occ["fecha_factura"])[:10] if occ["fecha_factura"] else "—"
            fecha_tanq_str = str(occ["fecha_tanqueo"])[:10] if occ["fecha_tanqueo"] else "—"
            L.append(f"| {i} | FC{occ['numdoctra']} | {fecha_fact_str} | {fecha_tanq_str} | "
                    f"{occ['bote'] or '—'} | {valor_str} | `{occ['archivo']}` |")
        L.append("")

        L.append("### Evidencia documental")
        L.append("")
        L.append("Para verificar el caso, consultar los archivos originales:")
        L.append("")
        for occ in occs:
            num = occ["numdoctra"]
            archivo = occ["archivo"]
            L.append(f"- **FC{num}**:")
            L.append(f"  - Factura: `G:\\Mi unidad\\...\\Facturas\\FC{num}\\FAC-FC{num}.pdf`")
            L.append(f"  - Remisión: `G:\\Mi unidad\\...\\Facturas\\FC{num}\\{archivo}`")
        L.append("")
        L.append("---")
        L.append("")

    L.append("## Solicitud formal")
    L.append("")
    L.append("Con base en la evidencia documental anterior, solicitamos comedidamente:")
    L.append("")
    L.append(f"1. La revisión de los **{len(cases)} casos** de remisiones duplicadas detectadas")
    L.append("2. La emisión de **notas crédito** por los montos confirmados como cobros duplicados")
    if total_monto_duplicado > 0:
        L.append(f"   (monto inicial estimado: **${total_monto_duplicado:,.0f}**, sujeto a verificación conjunta)")
    L.append("3. Una **explicación documentada** de los casos clasificados como 'requiere investigación'")
    L.append("4. Implementación de **controles internos** para prevenir reutilización de números de remisión")
    L.append("")
    L.append("Adjuntamos:")
    L.append("- `INFORME_DUPLICADOS.md` (este documento)")
    L.append("- `informe_duplicados.csv` (datos completos para análisis)")
    L.append("- Los PDFs de facturas y remisiones originales (rutas indicadas en cada caso)")
    L.append("")
    L.append("Quedamos atentos a su pronta respuesta.")
    L.append("")
    L.append("Cordialmente,")
    L.append("")
    L.append("Francisco Cortázar  ")
    L.append("Nautiturismo SAS  ")
    L.append("NIT 901.459.048")

    md_path.write_text("\n".join(L), encoding="utf-8")

    # Consola
    print("\n" + "=" * 70)
    print("  INFORME FORENSE — REMISIONES DUPLICADAS")
    print("=" * 70)
    print(f"  Números de remisión duplicados:    {len(cases)}")
    print(f"  Apariciones totales:                {total_apariciones}")
    print(f"  🔴 Casos confirmados (alto):        {casos_confirmados}")
    print(f"  🟠 Casos sospecha media:            {casos_sospechosos}")
    print(f"  🟡 Casos por investigar:            {casos_investigar}")
    print(f"  ✅ Descartados (cambio de sistema, >{gap_sistema_dias}d): {casos_no_aplica}")
    print("  " + "-" * 60)
    print(f"  💰 MONTO DUPLICADO REAL a recuperar: ${total_monto_duplicado:>12,.0f}")
    print("=" * 70)
    print(f"\n  Archivos generados en: {out_dir}")
    print(f"    • {csv_path.name}")
    print(f"    • {md_path.name}  ← informe formal forense")
    print("=" * 70)

    if cases:
        casos_relevantes = [c for c in cases if c["fuerza"] != "no_aplica"]
        if casos_relevantes:
            print(f"\n  TOP 5 casos relevantes (excluyendo cambio de sistema):")
            for c in sorted(casos_relevantes, key=lambda x: -x["monto_duplicado"])[:5]:
                gap = f"gap {c['gap_dias']}d" if c["gap_dias"] is not None else "gap ?"
                print(f"    Remisión #{c['rno']:>8}  →  {len(c['occurrences'])} facturas  "
                      f"${c['monto_duplicado']:>12,.0f}  [{c['fuerza']}, {gap}]")
        else:
            print(f"\n  ✅ Todos los duplicados se explican por cambio de sistema.")
            print(f"     NO hay casos relevantes para reclamar.")

    log.info("informe_duplicados_done",
             casos=len(cases), apariciones=total_apariciones,
             monto_duplicado=total_monto_duplicado,
             confirmados=casos_confirmados, sospechosos=casos_sospechosos,
             por_investigar=casos_investigar, no_aplica=casos_no_aplica,
             gap_sistema_dias=gap_sistema_dias)


def enviar_informe_email(control_path: Path, to_emails: list[str], cfg: dict,
                          log: RunLog) -> None:
    """Envia el informe + Excel anexo por email usando Gmail API.

    Reusa el mismo OAuth (scope gmail.modify ya incluye send).
    Asunto incluye 'BORRADOR' para que sea claro que es para revision interna.
    """
    from email.mime.multipart import MIMEMultipart
    from email.mime.base import MIMEBase
    from email.mime.text import MIMEText
    from email import encoders as email_encoders

    md_path = control_path.parent / "INFORME_RECLAMACION_TODOMAR.md"
    xlsx_path = control_path.parent / "ANEXO_RECLAMACION.xlsx"

    if not md_path.exists() or not xlsx_path.exists():
        log.error("informe_files_missing",
                  md_exists=md_path.exists(), xlsx_exists=xlsx_path.exists())
        print("\n  ⚠ No se encontraron los archivos del informe.")
        print("  Primero corre: python conciliador.py --informe-reclamacion")
        return

    log.info("enviando_email", to=to_emails)
    service = get_gmail_service(cfg, log)

    md_content = md_path.read_text(encoding="utf-8")
    # Extraer resumen ejecutivo del MD para el cuerpo del email
    body_intro = f"""Buen día,

Adjunto encontrarán el BORRADOR del informe de reclamación de facturas de
combustible para Todomar CHL S.A.S., generado a partir de la conciliación
automatizada del periodo analizado.

Por favor revisar:

1. INFORME_RECLAMACION_TODOMAR.md
   Documento formal con la argumentación caso por caso, listo para
   enviar a la contadora de Todomar (después de su aprobación).

2. ANEXO_RECLAMACION.xlsx
   Excel profesional con 4 hojas (Resumen, Casos Críticos, Sin Remisión,
   Diferencias). Las celdas de "PDF Factura" y "PDF Remisión" tienen
   hipervínculos clicables a los archivos originales en Drive para
   verificación visual de cada caso.

═══════════════════════════════════════════════════════════════════
                    EXTRACTO DEL INFORME
═══════════════════════════════════════════════════════════════════

"""
    # Tomar las primeras ~100 líneas del MD como preview
    md_preview = "\n".join(md_content.split("\n")[:80])
    body_intro += md_preview
    body_intro += "\n\n[...continúa en el archivo adjunto INFORME_RECLAMACION_TODOMAR.md...]"
    body_intro += "\n\n———\nGenerado automáticamente por el conciliador de combustible\n"
    body_intro += f"Fecha de generación: {datetime.now().strftime('%d/%m/%Y %H:%M')}"

    msg = MIMEMultipart("mixed")
    msg["Subject"] = (f"BORRADOR — Reclamación facturas combustible Todomar "
                      f"({datetime.now().strftime('%d/%m/%Y')})")
    msg["From"] = cfg["gmail_user"]
    msg["To"] = ", ".join(to_emails)

    msg.attach(MIMEText(body_intro, "plain", "utf-8"))

    # Adjuntar MD
    with md_path.open("rb") as f:
        part = MIMEBase("text", "markdown")
        part.set_payload(f.read())
        email_encoders.encode_base64(part)
        part.add_header("Content-Disposition",
                       f'attachment; filename="{md_path.name}"')
        msg.attach(part)

    # Adjuntar XLSX
    with xlsx_path.open("rb") as f:
        part = MIMEBase("application",
                       "vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        part.set_payload(f.read())
        email_encoders.encode_base64(part)
        part.add_header("Content-Disposition",
                       f'attachment; filename="{xlsx_path.name}"')
        msg.attach(part)

    # Enviar via Gmail API
    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    try:
        sent = service.users().messages().send(
            userId="me", body={"raw": raw}
        ).execute()
    except Exception as e:
        log.error("email_send_failed", err=str(e))
        print(f"\n  ❌ Error al enviar email: {e}")
        return

    log.info("email_sent", to=to_emails, message_id=sent.get("id"),
             thread_id=sent.get("threadId"))

    print("\n" + "=" * 72)
    print("  EMAIL ENVIADO")
    print("=" * 72)
    print(f"  De:        {cfg['gmail_user']}")
    print(f"  Para:      {', '.join(to_emails)}")
    print(f"  Asunto:    BORRADOR — Reclamación facturas combustible Todomar "
          f"({datetime.now().strftime('%d/%m/%Y')})")
    print(f"  Adjuntos:  {md_path.name}")
    print(f"             {xlsx_path.name}")
    print(f"  Message ID: {sent.get('id')}")
    print("=" * 72)
    print(f"\n  Revisa tu Gmail. El email tambien queda en 'Enviados' del")
    print(f"  remitente ({cfg['gmail_user']}).")
    print("=" * 72)


def generar_informe_reclamacion(control_path: Path, facturas_dir: Path,
                                 tolerance: float, log: RunLog) -> None:
    """Informe consolidado de reclamacion a Todomar.

    Combina los 3 tipos de inconsistencias detectadas:
      1. CRITICOS: factura inflada que reusa remision ya legitimamente cobrada
         -> factura ENTERA objetable
      2. SIN REMISION: factura llegada sin remision adjunta
         -> objetable mientras no envien remision
      3. SOBREFACTURA SIMPLE: factura > remision real (sin duplicacion)
         -> solo la DIFERENCIA es objetable

    Genera:
      - INFORME_RECLAMACION_TODOMAR.md (documento formal para email)
      - ANEXO_RECLAMACION.xlsx (Excel profesional con 4 hojas: Resumen,
        Criticos, Sin Remision, Diferencias)
    """
    import csv
    from collections import defaultdict

    wb = load_workbook(str(control_path), data_only=True)
    cons_ws = wb["Conciliación"]

    # === 1) Recopilar datos por NUMDOCTRA desde Conciliacion ===
    cons_index: dict = {}
    for r in range(2, cons_ws.max_row + 1):
        n = cons_ws.cell(row=r, column=COL["NUMDOCTRA"]).value
        if n is None:
            continue
        num_str = str(int(n) if isinstance(n, float) else n).strip()
        cons_index[num_str] = {
            "numdoctra": num_str,
            "fecha_factura": cons_ws.cell(row=r, column=COL["Fecha factura"]).value,
            "bote": cons_ws.cell(row=r, column=COL["Nombre de Bote"]).value,
            "valor_factura": cons_ws.cell(row=r, column=COL["Valor factura"]).value,
            "valor_remision": cons_ws.cell(row=r, column=COL["Valor remisión"]).value,
            "conciliacion": cons_ws.cell(row=r, column=COL["Conciliación"]).value or "",
            "diferencia": cons_ws.cell(row=r, column=COL["Valor (diferencia)"]).value,
            "observaciones": cons_ws.cell(row=r, column=COL["Observaciones"]).value or "",
        }

    # === 2) Detectar casos CRITICOS + capturar hora_tanqueo + computar flags ===
    criticos = []
    nums_en_criticos = set()
    # Indice {numdoctra: [{remision_no, valor_remision_det, bote_det, fecha_hora_tanqueo, archivo}]}
    # para enriquecer las "diferencias simples" con horas y deteccion de multi-bote
    detalle_por_factura: dict = defaultdict(list)

    if "Detalle Remisiones" in wb.sheetnames:
        det_ws = wb["Detalle Remisiones"]
        by_rno: dict = defaultdict(list)
        for r in range(2, det_ws.max_row + 1):
            numdoctra = det_ws.cell(row=r, column=DETALLE_COL["NUMDOCTRA Factura"]).value
            rno = det_ws.cell(row=r, column=DETALLE_COL["Remisión No."]).value
            if numdoctra is None:
                continue
            num_str = str(int(numdoctra) if isinstance(numdoctra, float) else numdoctra).strip()
            det_row = {
                "numdoctra": num_str,
                "remision_no": str(rno).strip() if rno is not None else None,
                "bote_det": det_ws.cell(row=r, column=DETALLE_COL["Bote"]).value,
                "fecha_hora_tanqueo": det_ws.cell(row=r, column=DETALLE_COL["Fecha tanqueo"]).value,
                "valor_remision_det": det_ws.cell(row=r, column=DETALLE_COL["Valor remisión"]).value,
                "archivo": det_ws.cell(row=r, column=DETALLE_COL["Archivo origen"]).value or "",
            }
            detalle_por_factura[num_str].append(det_row)
            if rno is not None:
                by_rno[str(rno).strip()].append(det_row)

        gap_dias_max = int(os.environ.get("CONCILIADOR_GAP_SISTEMA_DIAS", "365"))
        for rno, occs in by_rno.items():
            if len(set(o["numdoctra"] for o in occs)) < 2:
                continue
            fechas = []
            for o in occs:
                cd = cons_index.get(o["numdoctra"], {})
                f = _parse_fecha_safe(cd.get("fecha_factura"))
                if f:
                    fechas.append(f)
            gap_dias = (max(fechas) - min(fechas)).days if len(fechas) >= 2 else None
            if gap_dias is not None and gap_dias > gap_dias_max:
                continue  # cambio de sistema, no es caso real

            legitimas, infladas = [], []
            for o in occs:
                cd = cons_index.get(o["numdoctra"], {})
                vf = cd.get("valor_factura")
                vrd = o.get("valor_remision_det")
                if not isinstance(vf, (int, float)) or not isinstance(vrd, (int, float)):
                    continue
                merged = {**o, **cd}
                if abs(vf - vrd) <= tolerance:
                    legitimas.append(merged)
                elif vf > vrd + tolerance:
                    infladas.append(merged)

            if legitimas and infladas:
                vrr = min(l["valor_remision_det"] for l in legitimas)
                # === Computar flags por caso critico ===
                flags = []
                # Flag: sobrecobro negativo (algoritmo equivoco)
                for inf in infladas:
                    if inf["valor_factura"] - vrr <= 0:
                        flags.append("⚠ Sobrecobro negativo (revisar clasificacion)")
                        break
                # Flag: bote consolidado en alguna aparicion
                botes_concat = [str(x.get("bote") or "") for x in legitimas + infladas]
                if any("," in b for b in botes_concat):
                    flags.append("⚠ Bote consolidado (factura agrupa varios tanqueos)")
                # Flag: botes distintos entre legitimas e infladas
                # Normaliza: quita puntos, espacios extras, mayusculas — "L MARTI" == "L. MARTI"
                def _norm_bote(b):
                    if not b:
                        return ""
                    return re.sub(r"[\s.]+", "", str(b)).upper()
                botes_leg_norm = set(_norm_bote(l.get("bote")) for l in legitimas if l.get("bote"))
                botes_leg_norm.discard("")
                botes_inf_norm = set(_norm_bote(i.get("bote")) for i in infladas if i.get("bote"))
                botes_inf_norm.discard("")
                if botes_leg_norm and botes_inf_norm and not (botes_leg_norm & botes_inf_norm):
                    flags.append("⚠ Botes distintos entre legitima e inflada")
                # Flag: legitima con valor muy bajo (probable nota credito/ajuste)
                min_leg = min(l["valor_factura"] for l in legitimas
                             if isinstance(l.get("valor_factura"), (int, float)))
                max_inf = max(i["valor_factura"] for i in infladas
                             if isinstance(i.get("valor_factura"), (int, float)))
                if min_leg < 0.2 * max_inf:
                    flags.append("⚠ Legitima muy baja vs inflada (posible nota credito)")
                # Flag: gap temporal cerca del limite (200-365 dias)
                if gap_dias is not None and 200 < gap_dias <= gap_dias_max:
                    flags.append(f"⚠ Gap temporal cerca del limite ({gap_dias} dias)")
                # Flag: comparacion de hora_tanqueo
                horas_legitima = [_parse_fecha_safe(l.get("fecha_hora_tanqueo"))
                                 for l in legitimas]
                horas_inflada = [_parse_fecha_safe(i.get("fecha_hora_tanqueo"))
                                for i in infladas]
                horas_legitima = [h for h in horas_legitima if h]
                horas_inflada = [h for h in horas_inflada if h]
                if horas_legitima and horas_inflada:
                    hl = horas_legitima[0]
                    hi = horas_inflada[0]
                    delta_min = abs((hl - hi).total_seconds()) / 60
                    if delta_min < 30:
                        flags.append("✅ Hora tanqueo coincide — REFUERZA duplicado")
                    elif delta_min > 60:
                        flags.append("⚠ Hora tanqueo distinta — probable tanqueo diferente")

                for inf in infladas:
                    nums_en_criticos.add(inf["numdoctra"])
                criticos.append({
                    "rno": rno, "valor_remision_real": vrr,
                    "legitimas": legitimas, "infladas": infladas,
                    "monto_objetable": sum(i["valor_factura"] for i in infladas),
                    "flags": flags,
                    "gap_dias": gap_dias,
                })

    # === 3) Facturas SIN REMISION ===
    sin_remision = []
    for num, d in cons_index.items():
        if "no hay remisi" in d["conciliacion"].lower():
            sin_remision.append(d)

    # === 4) Diferencias SIMPLES (factura > remision, sin estar en criticos) ===
    diferencias_simples = []
    # Para detectar patron de diferencia recurrente (probable cargo fijo)
    diff_counts: dict = defaultdict(int)
    for num, d in cons_index.items():
        if num in nums_en_criticos:
            continue
        if "diferente" in d["conciliacion"].lower():
            diff = d.get("diferencia")
            if isinstance(diff, (int, float)) and diff > 0:
                diff_counts[round(diff)] += 1

    for num, d in cons_index.items():
        if num in nums_en_criticos:
            continue
        if "diferente" in d["conciliacion"].lower():
            diff = d.get("diferencia")
            if isinstance(diff, (int, float)) and diff > 0:
                # === Computar flags ===
                flags = []
                vf = d.get("valor_factura") or 0
                vr = d.get("valor_remision") or 0
                bote = str(d.get("bote") or "")
                # Flag: bote consolidado
                if "," in bote:
                    flags.append("⚠ Bote consolidado (factura agrupa varios tanqueos)")
                # Flag: ratio remision/factura muy bajo (Vision posible misread)
                if vf > 0 and vr / vf < 0.3:
                    pct = vr / vf * 100
                    flags.append(f"⚠ Ratio remision/factura bajo ({pct:.0f}%) - posible Vision misread")
                # Flag: diferencia recurrente (probable cargo fijo)
                if diff_counts.get(round(diff), 0) >= 3:
                    n_rec = diff_counts[round(diff)]
                    flags.append(f"⚠ Diferencia identica recurrente ({n_rec} facturas) - posible cargo fijo")
                # Flag: multi-tanqueo probable (1 remision pero factura >> remision)
                detalles = detalle_por_factura.get(num, [])
                n_remisiones_detectadas = len(detalles)
                if n_remisiones_detectadas == 1 and vr > 0 and vf > 2 * vr:
                    flags.append("⚠ Posible extraccion incompleta (1 remision pero factura > 2x)")

                # Enriquecer con horas
                horas_tanqueo = [_parse_fecha_safe(dr.get("fecha_hora_tanqueo"))
                                 for dr in detalles]
                horas_tanqueo_str = ", ".join(
                    str(h)[:19] for h in horas_tanqueo if h
                )

                d_with_flags = {**d, "flags": flags,
                                "horas_tanqueo": horas_tanqueo_str,
                                "n_remisiones_detectadas": n_remisiones_detectadas}
                diferencias_simples.append(d_with_flags)

    # === Totales (separados por: solidos sin flags vs con flags a verificar) ===
    criticos_solidos = [c for c in criticos if not c.get("flags") or
                        all("✅" in f for f in c.get("flags", []))]
    criticos_verificar = [c for c in criticos if c not in criticos_solidos]

    diferencias_solidas = [d for d in diferencias_simples if not d.get("flags")]
    diferencias_verificar = [d for d in diferencias_simples if d.get("flags")]

    total_criticos_solidos = sum(c["monto_objetable"] for c in criticos_solidos)
    total_criticos_verificar = sum(c["monto_objetable"] for c in criticos_verificar)
    total_criticos = total_criticos_solidos + total_criticos_verificar

    total_diferencias_solidas = sum(d["diferencia"] for d in diferencias_solidas
                                    if isinstance(d["diferencia"], (int, float)))
    total_diferencias_verificar = sum(d["diferencia"] for d in diferencias_verificar
                                      if isinstance(d["diferencia"], (int, float)))
    total_diferencias = total_diferencias_solidas + total_diferencias_verificar

    total_sin_rem = sum(d["valor_factura"] for d in sin_remision
                       if isinstance(d["valor_factura"], (int, float)))
    n_facturas_infladas = sum(len(c["infladas"]) for c in criticos)
    n_facturas_infladas_solidas = sum(len(c["infladas"]) for c in criticos_solidos)

    total_solido = total_criticos_solidos + total_diferencias_solidas
    total_verificar = total_criticos_verificar + total_diferencias_verificar
    total_reclamable_total = total_criticos + total_diferencias
    total_potencial_total = total_reclamable_total + total_sin_rem

    out_dir = control_path.parent

    # === Generar Excel anexo profesional ===
    xlsx_path = out_dir / "ANEXO_RECLAMACION.xlsx"
    _generar_excel_anexo_reclamacion(
        xlsx_path, criticos, sin_remision, diferencias_simples,
        total_criticos, total_sin_rem, total_diferencias,
        total_reclamable_total, total_potencial_total,
        n_facturas_infladas, facturas_dir,
        total_solido=total_solido, total_verificar=total_verificar,
        cons_index=cons_index, detalle_por_factura=detalle_por_factura,
    )

    # === Generar Markdown formal ===
    md_path = out_dir / "INFORME_RECLAMACION_TODOMAR.md"
    L = []
    L.append("# Informe de Reclamación de Facturas de Combustible")
    L.append("")
    L.append("**De:** Nautiturismo SAS (NIT 901.459.048)")
    L.append("**Para:** Departamento de Contabilidad — Todomar CHL S.A.S. (NIT 806.003.144)")
    L.append(f"**Fecha del informe:** {datetime.now().strftime('%d/%m/%Y')}")
    L.append("")
    L.append("---")
    L.append("")
    L.append("## 1. Resumen ejecutivo")
    L.append("")
    L.append("En el marco del proceso de conciliación de las facturas de combustible emitidas por")
    L.append("Todomar CHL S.A.S. a Nautiturismo SAS, identificamos tres tipos de inconsistencias que")
    L.append("requieren atención y resolución por parte de su departamento contable.")
    L.append("")
    L.append("### Cifras consolidadas")
    L.append("")
    L.append("| Categoría | Facturas | Monto |")
    L.append("|---|---:|---:|")
    L.append(f"| 🔴 Casos críticos (remisión duplicada + sobrefactura) | {n_facturas_infladas} | ${total_criticos:,.0f} |")
    L.append(f"| 🟡 Facturas sin remisión adjunta | {len(sin_remision)} | ${total_sin_rem:,.0f} |")
    L.append(f"| 🔴 Diferencias factura > remisión (sobrefactura simple) | {len(diferencias_simples)} | ${total_diferencias:,.0f} |")
    L.append(f"| **TOTAL OBJETABLE (reclamación directa)** | **{n_facturas_infladas + len(diferencias_simples)}** | **${total_reclamable_total:,.0f}** |")
    L.append(f"| **TOTAL POTENCIAL** (incluyendo sin remisión) | **{n_facturas_infladas + len(diferencias_simples) + len(sin_remision)}** | **${total_potencial_total:,.0f}** |")
    L.append("")
    L.append("Toda la evidencia documental que sustenta este informe se encuentra en el archivo")
    L.append("anexo **`ANEXO_RECLAMACION.xlsx`**, organizada en hojas por categoría con los")
    L.append("paths a los PDFs originales de cada factura y remisión.")
    L.append("")
    L.append("---")
    L.append("")

    # === Sección 2: Casos críticos ===
    L.append("## 2. Casos críticos — Remisión duplicada + sobrefactura")
    L.append("")
    if not criticos:
        L.append("*No se detectaron casos críticos en el periodo analizado.*")
        L.append("")
    else:
        L.append(f"Identificamos **{len(criticos)} casos** donde una misma Remisión No. fue utilizada")
        L.append(f"como soporte de **{n_facturas_infladas} facturas distintas** con valores superiores")
        L.append(f"al despacho real documentado. En estos casos, la factura inflada es **totalmente")
        L.append(f"objetable** porque su soporte (la remisión) ya fue legítimamente facturado en otra factura.")
        L.append("")
        L.append(f"**Monto total objetable por casos críticos: ${total_criticos:,.0f}**")
        L.append("")
        L.append("### Detalle (TOP 10 casos por monto)")
        L.append("")
        L.append("| # | Remisión | Factura LEGÍTIMA | Factura INFLADA | V. real | V. cobrado | Sobrecobro |")
        L.append("|---|---|---|---|---:|---:|---:|")
        for idx, c in enumerate(sorted(criticos, key=lambda x: -x["monto_objetable"])[:10], start=1):
            leg = c["legitimas"][0]
            for inf in c["infladas"]:
                L.append(f"| {idx} | {c['rno']} | FC{leg['numdoctra']} (${leg['valor_factura']:,.0f}) | "
                         f"FC{inf['numdoctra']} | ${c['valor_remision_real']:,.0f} | "
                         f"${inf['valor_factura']:,.0f} | +${inf['valor_factura'] - c['valor_remision_real']:,.0f} |")
        if len(criticos) > 10:
            L.append(f"| ... | y {len(criticos) - 10} casos más | | | | | |")
        L.append("")
        L.append("*Listado completo en hoja **Casos Críticos** del anexo Excel.*")
        L.append("")
    L.append("---")
    L.append("")

    # === Sección 3: Sin remisión ===
    L.append("## 3. Facturas sin remisión adjunta")
    L.append("")
    if not sin_remision:
        L.append("*No se detectaron facturas sin remisión en el periodo analizado.*")
        L.append("")
    else:
        L.append(f"Las siguientes **{len(sin_remision)} facturas** fueron emitidas por Todomar y enviadas")
        L.append("vía Facture, pero el archivo adjunto no contenía la remisión correspondiente como")
        L.append("evidencia del despacho.")
        L.append("")
        L.append(f"**Monto total facturado sin soporte documental: ${total_sin_rem:,.0f}**")
        L.append("")
        L.append("Solicitamos comedidamente el **reenvío de las remisiones correspondientes** para")
        L.append("soportar el despacho. En caso de que las remisiones no existan o no puedan ser")
        L.append("provistas, se procederá a objetar el cobro de estas facturas.")
        L.append("")
        L.append("### Detalle (TOP 10 por valor)")
        L.append("")
        L.append("| NUMDOCTRA | Fecha factura | Valor facturado |")
        L.append("|---|---|---:|")
        sorted_sin_rem = sorted(sin_remision,
                                key=lambda d: -(d["valor_factura"] if isinstance(d["valor_factura"], (int, float)) else 0))
        for d in sorted_sin_rem[:10]:
            vf = d["valor_factura"] if isinstance(d["valor_factura"], (int, float)) else 0
            fecha_str = str(d["fecha_factura"])[:10] if d["fecha_factura"] else "—"
            L.append(f"| FC{d['numdoctra']} | {fecha_str} | ${vf:,.0f} |")
        if len(sin_remision) > 10:
            L.append(f"| ... y {len(sin_remision) - 10} facturas más | | |")
        L.append(f"| **TOTAL** | | **${total_sin_rem:,.0f}** |")
        L.append("")
        L.append("*Listado completo en hoja **Sin Remisión** del anexo Excel.*")
        L.append("")
    L.append("---")
    L.append("")

    # === Sección 4: Diferencias simples ===
    L.append("## 4. Diferencias simples (factura > remisión, sin duplicación)")
    L.append("")
    if not diferencias_simples:
        L.append("*No se detectaron diferencias simples adicionales en el periodo analizado.*")
        L.append("")
    else:
        L.append(f"En las siguientes **{len(diferencias_simples)} facturas** el valor facturado supera al")
        L.append("valor del despacho documentado en la remisión adjunta. A diferencia de los casos")
        L.append("críticos (sección 2), aquí la remisión no está duplicada — solo el excedente es")
        L.append("objetable.")
        L.append("")
        L.append(f"**Monto total a reclamar por sobrefactura simple: ${total_diferencias:,.0f}**")
        L.append("")
        L.append("Solicitamos la emisión de nota crédito por el valor de la diferencia en cada caso.")
        L.append("")
        L.append("### Detalle (TOP 10 por diferencia)")
        L.append("")
        L.append("| NUMDOCTRA | Fecha | Bote | V. factura | V. remisión | Diferencia |")
        L.append("|---|---|---|---:|---:|---:|")
        sorted_diffs = sorted(diferencias_simples,
                              key=lambda d: -(d["diferencia"] if isinstance(d["diferencia"], (int, float)) else 0))
        for d in sorted_diffs[:10]:
            vf = d["valor_factura"] if isinstance(d["valor_factura"], (int, float)) else 0
            vr = d["valor_remision"] if isinstance(d["valor_remision"], (int, float)) else 0
            di = d["diferencia"] if isinstance(d["diferencia"], (int, float)) else 0
            fecha_str = str(d["fecha_factura"])[:10] if d["fecha_factura"] else "—"
            L.append(f"| FC{d['numdoctra']} | {fecha_str} | {d.get('bote') or '—'} | "
                     f"${vf:,.0f} | ${vr:,.0f} | +${di:,.0f} |")
        if len(diferencias_simples) > 10:
            L.append(f"| ... y {len(diferencias_simples) - 10} facturas más | | | | | |")
        L.append(f"| **TOTAL** | | | | | **${total_diferencias:,.0f}** |")
        L.append("")
        L.append("*Listado completo en hoja **Diferencias** del anexo Excel.*")
        L.append("")
    L.append("---")
    L.append("")

    # === Sección 5: Solicitud formal ===
    L.append("## 5. Solicitud formal")
    L.append("")
    L.append("Con base en la evidencia documental anterior, **solicitamos formalmente** a Todomar CHL S.A.S.:")
    L.append("")
    n_solicitud = 1
    if criticos:
        L.append(f"{n_solicitud}. **Emisión de nota crédito por ${total_criticos:,.0f}** correspondiente al")
        L.append(f"   monto íntegro de las {n_facturas_infladas} facturas infladas listadas en la **sección 2**")
        L.append(f"   (casos críticos), las cuales reutilizan remisiones ya legítimamente cobradas en otras")
        L.append(f"   facturas y carecen de soporte propio.")
        L.append("")
        n_solicitud += 1
    if diferencias_simples:
        L.append(f"{n_solicitud}. **Emisión de nota crédito por ${total_diferencias:,.0f}** correspondiente a")
        L.append(f"   las diferencias detectadas en las {len(diferencias_simples)} facturas listadas en la")
        L.append(f"   **sección 4**, donde el valor facturado supera al despacho real documentado.")
        L.append("")
        n_solicitud += 1
    if sin_remision:
        L.append(f"{n_solicitud}. **Reenvío de las remisiones correspondientes** a las {len(sin_remision)} facturas")
        L.append(f"   listadas en la **sección 3** (monto total ${total_sin_rem:,.0f}). En caso de no existir")
        L.append(f"   las remisiones, nota crédito por dicho valor.")
        L.append("")
        n_solicitud += 1
    L.append(f"{n_solicitud}. **Explicación formal** sobre los procesos internos que permitieron la reutilización")
    L.append(f"   de números de remisión como soporte de facturas distintas y las sobrefacturas detectadas.")
    L.append("")
    n_solicitud += 1
    L.append(f"{n_solicitud}. **Implementación de controles** que impidan que un mismo número de remisión sea")
    L.append(f"   adjuntado como soporte de más de una factura.")
    L.append("")
    n_solicitud += 1
    L.append(f"{n_solicitud}. **Auditoría conjunta** del periodo no analizado en este informe para verificar si")
    L.append(f"   el patrón se repite en otras facturas.")
    L.append("")
    L.append("---")
    L.append("")
    L.append("## 6. Anexos")
    L.append("")
    L.append("- **`INFORME_RECLAMACION_TODOMAR.md`** — este documento")
    L.append("- **`ANEXO_RECLAMACION.xlsx`** — Excel profesional con 4 hojas:")
    L.append("  - **Resumen** (cifras consolidadas + gráfica)")
    L.append("  - **Casos Críticos** (cada caso con legítima vs inflada(s), montos, paths a PDFs)")
    L.append("  - **Sin Remisión** (facturas sin soporte documental)")
    L.append("  - **Diferencias** (sobrefactura simple, con paths a PDFs)")
    L.append("- **PDFs originales** de las facturas y remisiones citadas (rutas indicadas en el Excel)")
    L.append("")
    L.append("---")
    L.append("")
    L.append("Quedamos atentos a su pronta respuesta para concertar reunión y dar seguimiento al")
    L.append("proceso de conciliación.")
    L.append("")
    L.append("Cordialmente,")
    L.append("")
    L.append("Francisco Cortázar  ")
    L.append("Nautiturismo SAS  ")
    L.append("NIT 901.459.048")

    md_path.write_text("\n".join(L), encoding="utf-8")

    # === Consola ===
    print("\n" + "=" * 72)
    print("  INFORME DE RECLAMACIÓN — Consolidado para Todomar")
    print("=" * 72)
    print(f"  Periodo analizado: archivo de control actual")
    print()
    print(f"  🔴 Casos críticos:                 {len(criticos):>4} casos / {n_facturas_infladas:>4} facturas  ${total_criticos:>14,.0f}")
    print(f"  🟡 Sin remisión adjunta:           {len(sin_remision):>4} facturas{'':>16}${total_sin_rem:>14,.0f}")
    print(f"  🔴 Diferencias simples:            {len(diferencias_simples):>4} facturas{'':>16}${total_diferencias:>14,.0f}")
    print("  " + "-" * 64)
    print(f"  💰 TOTAL OBJETABLE (directo):                            ${total_reclamable_total:>14,.0f}")
    print(f"  📊 TOTAL POTENCIAL (incl. sin remisión):                 ${total_potencial_total:>14,.0f}")
    print("=" * 72)
    print(f"\n  Archivos generados en: {out_dir}")
    print(f"    • INFORME_RECLAMACION_TODOMAR.md  ← copiar al cuerpo del email")
    print(f"    • ANEXO_RECLAMACION.xlsx          ← adjuntar al email")
    print("=" * 72)

    log.info("informe_reclamacion_done",
             criticos=len(criticos), facturas_infladas=n_facturas_infladas,
             sin_remision=len(sin_remision), diferencias=len(diferencias_simples),
             total_criticos=total_criticos, total_sin_rem=total_sin_rem,
             total_diferencias=total_diferencias,
             total_reclamable=total_reclamable_total,
             total_potencial=total_potencial_total)


def _generar_excel_anexo_reclamacion(
    xlsx_path: Path, criticos: list, sin_remision: list, diferencias: list,
    tot_crit: float, tot_sin_rem: float, tot_dif: float,
    tot_reclam: float, tot_potencial: float, n_infladas: int,
    facturas_dir: Path,
    total_solido: float = 0, total_verificar: float = 0,
    cons_index: dict | None = None,
    detalle_por_factura: dict | None = None,
) -> None:
    """Genera Excel profesional anexo con 4 hojas."""
    wb = Workbook()

    header_font = Font(bold=True, color="FFFFFF", size=11)
    header_fill = PatternFill("solid", fgColor="305496")
    money_font = Font(bold=True, size=12)
    title_font = Font(bold=True, size=16, color="1F4E79")
    total_font = Font(bold=True, size=12, color="9C0006")
    centered = Alignment(horizontal="center", vertical="center", wrap_text=True)

    # =============== HOJA RESUMEN ===============
    ws = wb.active
    ws.title = "Resumen"
    ws.sheet_view.showGridLines = False
    ws.merge_cells("A1:D1")
    ws["A1"] = "ANEXO — Reclamación a Todomar CHL S.A.S."
    ws["A1"].font = title_font
    ws["A1"].alignment = centered
    ws.row_dimensions[1].height = 32

    ws["A3"] = f"Fecha: {datetime.now().strftime('%d/%m/%Y')}"
    ws["A4"] = "De: Nautiturismo SAS (NIT 901.459.048)"
    ws["A5"] = "Para: Departamento de Contabilidad — Todomar CHL S.A.S. (NIT 806.003.144)"

    # Tabla cifras
    ws["A7"] = "Categoría"
    ws["B7"] = "Cantidad"
    ws["C7"] = "Monto"
    for c in ["A7", "B7", "C7"]:
        ws[c].font = header_font
        ws[c].fill = header_fill
        ws[c].alignment = centered
        ws[c].border = THIN_BORDER

    rows_resumen = [
        ("🔴 Casos críticos (remisión duplicada + sobrefactura)", n_infladas, tot_crit, "FCE4E4"),
        ("🟡 Facturas sin remisión adjunta", len(sin_remision), tot_sin_rem, "FFF2CC"),
        ("🔴 Diferencias factura > remisión (sobrefactura simple)", len(diferencias), tot_dif, "FCE4E4"),
    ]
    for i, (label, cant, monto, color) in enumerate(rows_resumen, start=8):
        ws.cell(row=i, column=1, value=label).fill = PatternFill("solid", fgColor=color)
        ws.cell(row=i, column=2, value=cant).fill = PatternFill("solid", fgColor=color)
        ws.cell(row=i, column=2).alignment = centered
        c = ws.cell(row=i, column=3, value=monto)
        c.number_format = MONEY_FMT
        c.font = money_font
        c.fill = PatternFill("solid", fgColor=color)
        for col_letter in ["A", "B", "C"]:
            ws[f"{col_letter}{i}"].border = THIN_BORDER

    # SUBTOTALES separados: solido vs verificar
    solido_fill = PatternFill("solid", fgColor="E2F0D9")  # verde claro
    verificar_fill = PatternFill("solid", fgColor="FFE699")  # amarillo
    ws.cell(row=12, column=1, value="✅ TOTAL SÓLIDO (sin flags) - reclamar firme").font = Font(bold=True, size=11)
    ws.cell(row=12, column=1).fill = solido_fill
    c = ws.cell(row=12, column=3, value=total_solido)
    c.font = Font(bold=True, color="385723")
    c.number_format = MONEY_FMT
    c.fill = solido_fill

    ws.cell(row=13, column=1, value="⚠ TOTAL A VERIFICAR (con flags) - revisar manualmente").font = Font(bold=True, size=11)
    ws.cell(row=13, column=1).fill = verificar_fill
    c = ws.cell(row=13, column=3, value=total_verificar)
    c.font = Font(bold=True, color="9C5700")
    c.number_format = MONEY_FMT
    c.fill = verificar_fill

    # TOTAL OBJETABLE
    ws.cell(row=15, column=1, value="TOTAL OBJETABLE (reclamación directa: sólido + a verificar)").font = total_font
    ws.cell(row=15, column=1).fill = PatternFill("solid", fgColor="FCE4E4")
    ws.cell(row=15, column=2, value=n_infladas + len(diferencias)).font = total_font
    c = ws.cell(row=15, column=3, value=tot_reclam)
    c.font = total_font
    c.number_format = MONEY_FMT
    c.fill = PatternFill("solid", fgColor="FCE4E4")
    for col_letter in ["A", "B", "C"]:
        ws[f"{col_letter}15"].border = THIN_BORDER

    ws.cell(row=16, column=1, value="TOTAL POTENCIAL (incl. sin remisión)").font = Font(bold=True, size=11)
    ws.cell(row=16, column=2, value=n_infladas + len(diferencias) + len(sin_remision)).font = Font(bold=True)
    c = ws.cell(row=16, column=3, value=tot_potencial)
    c.font = Font(bold=True, size=11)
    c.number_format = MONEY_FMT
    for col_letter in ["A", "B", "C"]:
        ws[f"{col_letter}16"].border = THIN_BORDER

    # Leyenda
    ws.cell(row=18, column=1, value="Leyenda de filas en las hojas siguientes:").font = Font(italic=True, size=10)
    ws.cell(row=19, column=1, value="  • Fondo verde claro: sin flags (caso sólido)").font = Font(italic=True, size=10, color="385723")
    ws.cell(row=20, column=1, value="  • Fondo amarillo: con flag(s) — ver columna 'Flag / Sospecha'").font = Font(italic=True, size=10, color="9C5700")
    ws.cell(row=21, column=1, value="  • Columnas con paths a PDFs son hipervínculos clicables").font = Font(italic=True, size=10, color="595959")

    ws.column_dimensions["A"].width = 55
    ws.column_dimensions["B"].width = 12
    ws.column_dimensions["C"].width = 22

    # Nota
    ws.merge_cells("A15:D15")
    ws["A15"] = "Las hojas siguientes contienen el detalle por categoría con paths a los PDFs originales."
    ws["A15"].font = Font(italic=True, size=10, color="595959")

    # =============== HOJA CASOS CRÍTICOS ===============
    ws2 = wb.create_sheet("Casos Críticos")
    headers_crit = ["Remisión No.", "Factura LEGÍTIMA", "Fecha legítima",
                    "Hora tanqueo leg.", "Bote legítima",
                    "V. factura legítima", "V. remisión real",
                    "Factura INFLADA", "Fecha inflada", "Hora tanqueo infl.",
                    "Bote inflada",
                    "V. factura inflada", "Sobrecobro", "Monto objetable",
                    "Flag / Sospecha", "PDF Factura inflada", "PDF Remisión inflada"]
    for i, h in enumerate(headers_crit, start=1):
        c = ws2.cell(row=1, column=i, value=h)
        c.font = header_font
        c.fill = header_fill
        c.alignment = centered
        c.border = THIN_BORDER
    ws2.row_dimensions[1].height = 36
    ws2.freeze_panes = "A2"

    flag_fill = PatternFill("solid", fgColor="FFE699")  # amarillo para filas con flag
    row = 2
    for c in sorted(criticos, key=lambda x: -x["monto_objetable"]):
        leg = c["legitimas"][0]
        flags_str = " | ".join(c.get("flags", []))
        has_flag = bool(c.get("flags"))
        for inf in c["infladas"]:
            ws2.cell(row=row, column=1, value=c["rno"])
            ws2.cell(row=row, column=2, value=f"FC{leg['numdoctra']}")
            ws2.cell(row=row, column=3, value=str(leg.get("fecha_factura") or "")[:10])
            ws2.cell(row=row, column=4, value=str(leg.get("fecha_hora_tanqueo") or "")[:19])
            ws2.cell(row=row, column=5, value=leg.get("bote") or "")
            cf_leg = ws2.cell(row=row, column=6, value=leg.get("valor_factura"))
            cf_leg.number_format = MONEY_FMT
            cr = ws2.cell(row=row, column=7, value=c["valor_remision_real"])
            cr.number_format = MONEY_FMT
            ws2.cell(row=row, column=8, value=f"FC{inf['numdoctra']}")
            ws2.cell(row=row, column=9, value=str(inf.get("fecha_factura") or "")[:10])
            ws2.cell(row=row, column=10, value=str(inf.get("fecha_hora_tanqueo") or "")[:19])
            ws2.cell(row=row, column=11, value=inf.get("bote") or "")
            cf_inf = ws2.cell(row=row, column=12, value=inf["valor_factura"])
            cf_inf.number_format = MONEY_FMT
            cs = ws2.cell(row=row, column=13, value=inf["valor_factura"] - c["valor_remision_real"])
            cs.number_format = MONEY_FMT
            co = ws2.cell(row=row, column=14, value=inf["valor_factura"])
            co.number_format = MONEY_FMT
            co.font = Font(bold=True, color="9C0006")
            # Flag
            cflag = ws2.cell(row=row, column=15, value=flags_str)
            cflag.alignment = Alignment(wrap_text=True, vertical="center")
            # Hyperlinks
            path_fac = facturas_dir / f"FC{inf['numdoctra']}" / f"FAC-FC{inf['numdoctra']}.pdf"
            path_rem = facturas_dir / f"FC{inf['numdoctra']}" / inf.get("archivo", "")
            set_hyperlink_cell(ws2.cell(row=row, column=16), path_fac, f"FAC-FC{inf['numdoctra']}.pdf")
            set_hyperlink_cell(ws2.cell(row=row, column=17), path_rem, inf.get("archivo", ""))
            for col_idx in range(1, 18):
                ws2.cell(row=row, column=col_idx).border = THIN_BORDER
                if has_flag:
                    ws2.cell(row=row, column=col_idx).fill = flag_fill
                elif row % 2 == 0:
                    ws2.cell(row=row, column=col_idx).fill = ZEBRA_FILL
            row += 1

    # Total
    ws2.cell(row=row, column=13, value="TOTAL OBJETABLE:").font = total_font
    ct = ws2.cell(row=row, column=14, value=tot_crit)
    ct.number_format = MONEY_FMT
    ct.font = total_font
    for letter in ["A", "B", "C", "D", "E", "F", "G", "H", "I", "J", "K", "L", "M", "N"]:
        ws2[f"{letter}{row}"].fill = PatternFill("solid", fgColor="FCE4E4")

    widths_crit = {"A": 12, "B": 12, "C": 12, "D": 18, "E": 16, "F": 16, "G": 16,
                   "H": 12, "I": 12, "J": 18, "K": 16, "L": 16, "M": 14, "N": 16,
                   "O": 50, "P": 22, "Q": 28}
    for letter, w in widths_crit.items():
        ws2.column_dimensions[letter].width = w
    ws2.auto_filter.ref = f"A1:Q{row-1}"

    # =============== HOJA SIN REMISIÓN ===============
    ws3 = wb.create_sheet("Sin Remisión")
    headers_sr = ["NUMDOCTRA", "Fecha factura", "Valor facturado", "PDF Factura"]
    for i, h in enumerate(headers_sr, start=1):
        c = ws3.cell(row=1, column=i, value=h)
        c.font = header_font
        c.fill = header_fill
        c.alignment = centered
        c.border = THIN_BORDER
    ws3.row_dimensions[1].height = 28
    ws3.freeze_panes = "A2"

    sorted_sr = sorted(sin_remision,
                       key=lambda d: -(d["valor_factura"] if isinstance(d["valor_factura"], (int, float)) else 0))
    row = 2
    for d in sorted_sr:
        ws3.cell(row=row, column=1, value=f"FC{d['numdoctra']}")
        ws3.cell(row=row, column=2, value=str(d["fecha_factura"])[:10] if d["fecha_factura"] else "")
        cv = ws3.cell(row=row, column=3, value=d["valor_factura"])
        cv.number_format = MONEY_FMT
        path_fac = facturas_dir / f"FC{d['numdoctra']}" / f"FAC-FC{d['numdoctra']}.pdf"
        set_hyperlink_cell(ws3.cell(row=row, column=4), path_fac, f"FAC-FC{d['numdoctra']}.pdf")
        for col_idx in range(1, 5):
            ws3.cell(row=row, column=col_idx).border = THIN_BORDER
            if row % 2 == 0:
                ws3.cell(row=row, column=col_idx).fill = ZEBRA_FILL
        row += 1
    # Total
    ws3.cell(row=row, column=2, value="TOTAL:").font = total_font
    ct = ws3.cell(row=row, column=3, value=tot_sin_rem)
    ct.number_format = MONEY_FMT
    ct.font = total_font
    for col_letter in ["A", "B", "C", "D"]:
        ws3[f"{col_letter}{row}"].fill = PatternFill("solid", fgColor="FFF2CC")
    ws3.column_dimensions["A"].width = 14
    ws3.column_dimensions["B"].width = 14
    ws3.column_dimensions["C"].width = 20
    ws3.column_dimensions["D"].width = 32
    ws3.auto_filter.ref = f"A1:D{row-1}"

    # =============== HOJA DIFERENCIAS ===============
    ws4 = wb.create_sheet("Diferencias")
    headers_df = ["NUMDOCTRA", "Fecha factura", "Bote", "# Rem detectadas",
                  "Horas tanqueo", "V. factura", "V. remisión",
                  "Diferencia (a reclamar)", "Flag / Sospecha",
                  "PDF Factura", "PDF Remisión"]
    for i, h in enumerate(headers_df, start=1):
        c = ws4.cell(row=1, column=i, value=h)
        c.font = header_font
        c.fill = header_fill
        c.alignment = centered
        c.border = THIN_BORDER
    ws4.row_dimensions[1].height = 36
    ws4.freeze_panes = "A2"

    flag_fill = PatternFill("solid", fgColor="FFE699")
    sorted_df = sorted(diferencias,
                       key=lambda d: -(d["diferencia"] if isinstance(d["diferencia"], (int, float)) else 0))
    row = 2
    for d in sorted_df:
        has_flag = bool(d.get("flags"))
        flags_str = " | ".join(d.get("flags", []))
        ws4.cell(row=row, column=1, value=f"FC{d['numdoctra']}")
        ws4.cell(row=row, column=2, value=str(d["fecha_factura"])[:10] if d["fecha_factura"] else "")
        ws4.cell(row=row, column=3, value=d.get("bote") or "")
        ws4.cell(row=row, column=4, value=d.get("n_remisiones_detectadas") or 0)
        ws4.cell(row=row, column=5, value=d.get("horas_tanqueo") or "")
        cf = ws4.cell(row=row, column=6, value=d["valor_factura"])
        cf.number_format = MONEY_FMT
        cr = ws4.cell(row=row, column=7, value=d["valor_remision"])
        cr.number_format = MONEY_FMT
        cd = ws4.cell(row=row, column=8, value=d["diferencia"])
        cd.number_format = MONEY_FMT
        cd.font = Font(bold=True, color="9C0006")
        cflag = ws4.cell(row=row, column=9, value=flags_str)
        cflag.alignment = Alignment(wrap_text=True, vertical="center")
        path_fac = facturas_dir / f"FC{d['numdoctra']}" / f"FAC-FC{d['numdoctra']}.pdf"
        path_rem = facturas_dir / f"FC{d['numdoctra']}" / f"REM-FC{d['numdoctra']}.pdf"
        set_hyperlink_cell(ws4.cell(row=row, column=10), path_fac, f"FAC-FC{d['numdoctra']}.pdf")
        set_hyperlink_cell(ws4.cell(row=row, column=11), path_rem, f"REM-FC{d['numdoctra']}.pdf")
        for col_idx in range(1, 12):
            ws4.cell(row=row, column=col_idx).border = THIN_BORDER
            if has_flag:
                ws4.cell(row=row, column=col_idx).fill = flag_fill
            elif row % 2 == 0:
                ws4.cell(row=row, column=col_idx).fill = ZEBRA_FILL
        row += 1
    # Total
    ws4.cell(row=row, column=7, value="TOTAL A RECLAMAR:").font = total_font
    ct = ws4.cell(row=row, column=8, value=tot_dif)
    ct.number_format = MONEY_FMT
    ct.font = total_font
    for letter in ["A", "B", "C", "D", "E", "F", "G", "H", "I", "J", "K"]:
        ws4[f"{letter}{row}"].fill = PatternFill("solid", fgColor="FCE4E4")
    widths_df = {"A": 12, "B": 12, "C": 28, "D": 14, "E": 30, "F": 16, "G": 16,
                 "H": 18, "I": 50, "J": 22, "K": 22}
    for letter, w in widths_df.items():
        ws4.column_dimensions[letter].width = w
    ws4.auto_filter.ref = f"A1:K{row-1}"

    # =============== HOJA UNIVERSO COMPLETO ===============
    if cons_index:
        ws5 = wb.create_sheet("Universo Completo")
        headers_uni = ["NUMDOCTRA", "Fecha factura", "Bote", "Valor factura",
                       "Valor remisión", "# Remisiones", "Conciliación",
                       "Diferencia", "Observaciones", "PDF Factura", "PDF Remisión"]
        for i, h in enumerate(headers_uni, start=1):
            c = ws5.cell(row=1, column=i, value=h)
            c.font = header_font
            c.fill = header_fill
            c.alignment = centered
            c.border = THIN_BORDER
        ws5.row_dimensions[1].height = 32
        ws5.freeze_panes = "A2"

        # Fills por estado
        fill_ok = PatternFill("solid", fgColor="E2F0D9")
        fill_amarillo = PatternFill("solid", fgColor="FFF2CC")
        fill_rojo = PatternFill("solid", fgColor="FCE4E4")
        fill_naranja = PatternFill("solid", fgColor="FCE6C9")
        fill_sin_correo = PatternFill("solid", fgColor="FFE699")

        # Ordenar por NUMDOCTRA (numérico)
        def _sort_key(num_str):
            try:
                return int(num_str)
            except (ValueError, TypeError):
                return 0
        sorted_nums = sorted(cons_index.keys(), key=_sort_key)

        # Contadores para el resumen al final
        contadores = {"OK": 0, "Sin remisión": 0, "Diferente": 0,
                     "Pendiente": 0, "Sin correo": 0, "Otro": 0}
        montos = {"OK": 0.0, "Sin remisión": 0.0, "Diferente": 0.0,
                 "Pendiente": 0.0, "Sin correo": 0.0, "Otro": 0.0}

        row = 2
        for num in sorted_nums:
            d = cons_index[num]
            conc = str(d.get("conciliacion") or "")
            obs = str(d.get("observaciones") or "")
            vf = d.get("valor_factura") if isinstance(d.get("valor_factura"), (int, float)) else 0

            # Determinar fill + categoria
            fill = None
            cat = "Otro"
            if "OK" in conc and "Pendiente" not in conc:
                fill, cat = fill_ok, "OK"
            elif "No hay remisi" in conc.lower():
                fill, cat = fill_amarillo, "Sin remisión"
            elif "diferente" in conc.lower():
                fill, cat = fill_rojo, "Diferente"
            elif "Pendiente" in conc:
                fill, cat = fill_naranja, "Pendiente"
            elif "No se encontró" in obs or "No se encontro" in obs:
                fill, cat = fill_sin_correo, "Sin correo"
            contadores[cat] += 1
            montos[cat] += vf

            # # remisiones
            n_rem = len(detalle_por_factura.get(num, [])) if detalle_por_factura else 0

            ws5.cell(row=row, column=1, value=f"FC{num}")
            ws5.cell(row=row, column=2, value=str(d.get("fecha_factura") or "")[:10])
            ws5.cell(row=row, column=3, value=d.get("bote") or "")
            c_vf = ws5.cell(row=row, column=4, value=d.get("valor_factura"))
            if isinstance(d.get("valor_factura"), (int, float)):
                c_vf.number_format = MONEY_FMT
            c_vr = ws5.cell(row=row, column=5, value=d.get("valor_remision"))
            if isinstance(d.get("valor_remision"), (int, float)):
                c_vr.number_format = MONEY_FMT
            ws5.cell(row=row, column=6, value=n_rem)
            ws5.cell(row=row, column=7, value=conc)
            c_dif = ws5.cell(row=row, column=8, value=d.get("diferencia"))
            if isinstance(d.get("diferencia"), (int, float)):
                c_dif.number_format = MONEY_FMT
            c_obs = ws5.cell(row=row, column=9, value=obs)
            c_obs.alignment = Alignment(wrap_text=True, vertical="center")
            # Hyperlinks
            path_fac = facturas_dir / f"FC{num}" / f"FAC-FC{num}.pdf"
            path_rem = facturas_dir / f"FC{num}" / f"REM-FC{num}.pdf"
            if path_fac.exists() or cat != "Sin correo":
                set_hyperlink_cell(ws5.cell(row=row, column=10), path_fac, f"FAC-FC{num}.pdf")
            if path_rem.exists() or cat in ("OK", "Diferente", "Pendiente"):
                set_hyperlink_cell(ws5.cell(row=row, column=11), path_rem, f"REM-FC{num}.pdf")
            # Aplicar fill
            if fill:
                for col_idx in range(1, 12):
                    ws5.cell(row=row, column=col_idx).fill = fill
                    ws5.cell(row=row, column=col_idx).border = THIN_BORDER
            row += 1

        # Fila TOTAL al final
        ws5.cell(row=row, column=3, value="TOTAL UNIVERSO:").font = total_font
        ws5.cell(row=row, column=4, value=sum(montos.values())).number_format = MONEY_FMT
        ws5.cell(row=row, column=4).font = total_font
        for letter in ["A", "B", "C", "D", "E", "F", "G", "H", "I", "J", "K"]:
            ws5[f"{letter}{row}"].fill = PatternFill("solid", fgColor="D9E1F2")

        # Resumen al lado (cols M-O), 2 filas por estado
        ws5.cell(row=1, column=13, value="RESUMEN POR ESTADO").font = Font(bold=True, size=12)
        ws5.cell(row=1, column=13).fill = header_fill
        ws5.cell(row=1, column=13).font = Font(bold=True, color="FFFFFF", size=12)
        for letter in ["M", "N", "O"]:
            ws5[f"{letter}1"].fill = header_fill
        ws5.cell(row=2, column=13, value="Estado")
        ws5.cell(row=2, column=14, value="Cantidad")
        ws5.cell(row=2, column=15, value="Monto facturado")
        for c_letter in ["M2", "N2", "O2"]:
            ws5[c_letter].font = Font(bold=True)
            ws5[c_letter].fill = PatternFill("solid", fgColor="D9E1F2")
        emoji_map = {"OK": "🟢 OK", "Sin remisión": "🟡 Sin remisión",
                     "Diferente": "🔴 Diferente", "Pendiente": "🟠 Pendiente",
                     "Sin correo": "📭 Sin correo", "Otro": "❓ Otro"}
        fill_map = {"OK": fill_ok, "Sin remisión": fill_amarillo,
                   "Diferente": fill_rojo, "Pendiente": fill_naranja,
                   "Sin correo": fill_sin_correo, "Otro": None}
        rr = 3
        for cat in ["OK", "Sin remisión", "Diferente", "Pendiente", "Sin correo", "Otro"]:
            if contadores[cat] == 0 and cat == "Otro":
                continue
            ws5.cell(row=rr, column=13, value=emoji_map[cat])
            ws5.cell(row=rr, column=14, value=contadores[cat])
            cm = ws5.cell(row=rr, column=15, value=montos[cat])
            cm.number_format = MONEY_FMT
            if fill_map[cat]:
                for letter in ["M", "N", "O"]:
                    ws5[f"{letter}{rr}"].fill = fill_map[cat]
            rr += 1
        # Total resumen
        ws5.cell(row=rr, column=13, value="TOTAL").font = total_font
        ws5.cell(row=rr, column=14, value=sum(contadores.values())).font = total_font
        ct = ws5.cell(row=rr, column=15, value=sum(montos.values()))
        ct.number_format = MONEY_FMT
        ct.font = total_font
        for letter in ["M", "N", "O"]:
            ws5[f"{letter}{rr}"].fill = PatternFill("solid", fgColor="D9E1F2")

        widths_uni = {"A": 12, "B": 12, "C": 22, "D": 16, "E": 16, "F": 10,
                      "G": 32, "H": 14, "I": 40, "J": 22, "K": 22,
                      "M": 22, "N": 12, "O": 18}
        for letter, w in widths_uni.items():
            ws5.column_dimensions[letter].width = w
        ws5.auto_filter.ref = f"A1:K{row-1}"

    wb.save(str(xlsx_path))


def generar_informe_criticos(control_path: Path, facturas_dir: Path,
                              tolerance: float, log: RunLog) -> None:
    """Informe CRITICO: detecta el patron forense mas fuerte =
    remision duplicada + sobrefactura (factura inflada que reusa una
    remision ya legitimamente facturada).

    Para cada remision_no con apariciones multiples:
    1. Si gap temporal > 365 dias -> descartar (cambio de sistema)
    2. Identificar 'legitima(s)': factura value ≈ remision value (dentro de tolerancia)
    3. Identificar 'inflada(s)': factura value > remision value + tolerancia
    4. Si HAY ambas (legitima + inflada) = caso critico
       La inflada es totalmente objetable: usa una remision ya cobrada como soporte

    Output:
      - informe_criticos.csv (lineas planas por caso)
      - INFORME_CRITICOS.md (caso por caso, presentable a contadora de Todomar)
    """
    import csv
    from collections import defaultdict

    wb = load_workbook(str(control_path), data_only=True)
    if "Detalle Remisiones" not in wb.sheetnames:
        print("\n  ⚠ Hoja 'Detalle Remisiones' no existe. Reprocesa con la version actual.")
        return

    # 1) Indice de Conciliacion: numdoctra -> datos completos
    cons_ws = wb["Conciliación"]
    cons_index: dict = {}
    for r in range(2, cons_ws.max_row + 1):
        n = cons_ws.cell(row=r, column=COL["NUMDOCTRA"]).value
        if n is None:
            continue
        num_str = str(int(n) if isinstance(n, float) else n).strip()
        cons_index[num_str] = {
            "fecha_factura": cons_ws.cell(row=r, column=COL["Fecha factura"]).value,
            "bote": cons_ws.cell(row=r, column=COL["Nombre de Bote"]).value,
            "valor_factura": cons_ws.cell(row=r, column=COL["Valor factura"]).value,
            "valor_remision": cons_ws.cell(row=r, column=COL["Valor remisión"]).value,
            "n_remisiones": cons_ws.cell(row=r, column=COL["# Remisiones"]).value,
            "conciliacion": cons_ws.cell(row=r, column=COL["Conciliación"]).value or "",
            "diferencia": cons_ws.cell(row=r, column=COL["Valor (diferencia)"]).value,
        }

    # 2) Agrupar Detalle Remisiones por remision_no
    det_ws = wb["Detalle Remisiones"]
    by_rno: dict = defaultdict(list)
    for r in range(2, det_ws.max_row + 1):
        numdoctra = det_ws.cell(row=r, column=DETALLE_COL["NUMDOCTRA Factura"]).value
        rno = det_ws.cell(row=r, column=DETALLE_COL["Remisión No."]).value
        if numdoctra is None or rno is None:
            continue
        num_str = str(int(numdoctra) if isinstance(numdoctra, float) else numdoctra).strip()
        by_rno[str(rno).strip()].append({
            "numdoctra": num_str,
            "bote_det": det_ws.cell(row=r, column=DETALLE_COL["Bote"]).value,
            "fecha_tanqueo": det_ws.cell(row=r, column=DETALLE_COL["Fecha tanqueo"]).value,
            "valor_remision_det": det_ws.cell(row=r, column=DETALLE_COL["Valor remisión"]).value,
            "archivo": det_ws.cell(row=r, column=DETALLE_COL["Archivo origen"]).value or "",
        })

    gap_sistema_dias = int(os.environ.get("CONCILIADOR_GAP_SISTEMA_DIAS", "365"))

    # 3) Detectar casos criticos
    criticos = []
    for rno, occurrences in by_rno.items():
        unique_nums = set(o["numdoctra"] for o in occurrences)
        if len(unique_nums) < 2:
            continue

        # Filtro gap sistema
        fechas = []
        for o in occurrences:
            cdata = cons_index.get(o["numdoctra"], {})
            f = _parse_fecha_safe(cdata.get("fecha_factura")) or _parse_fecha_safe(o.get("fecha_tanqueo"))
            if f:
                fechas.append(f)
        if len(fechas) >= 2:
            gap = (max(fechas) - min(fechas)).days
            if gap > gap_sistema_dias:
                continue  # cambio de sistema, no es caso real

        # Clasificar cada aparicion: legitima / inflada
        legitimas = []
        infladas = []
        sin_clasificar = []
        for o in occurrences:
            cdata = cons_index.get(o["numdoctra"], {})
            vf = cdata.get("valor_factura")
            vr_det = o.get("valor_remision_det")  # valor leido de la remision en esta factura
            if not isinstance(vf, (int, float)) or not isinstance(vr_det, (int, float)):
                sin_clasificar.append({**o, **cdata})
                continue
            if abs(vf - vr_det) <= tolerance:
                legitimas.append({**o, **cdata})
            elif vf > vr_det + tolerance:
                infladas.append({**o, **cdata})
            else:
                # vf < vr_det: factura menor que remision (raro), agregar a sin_clasificar
                sin_clasificar.append({**o, **cdata})

        if not legitimas or not infladas:
            continue  # no es caso critico (no hay duplicacion + inflado conjunto)

        # Es caso critico
        # La remision real tiene valor = min legitimo (o promedio si varios)
        valor_remision_real = min(l.get("valor_remision_det", 0) for l in legitimas)

        monto_objetable = sum(i["valor_factura"] for i in infladas)
        monto_duplicado = valor_remision_real * len(infladas)
        monto_sobrefactura = monto_objetable - monto_duplicado

        criticos.append({
            "rno": rno,
            "valor_remision_real": valor_remision_real,
            "legitimas": legitimas,
            "infladas": infladas,
            "sin_clasificar": sin_clasificar,
            "monto_objetable": monto_objetable,
            "monto_duplicado": monto_duplicado,
            "monto_sobrefactura": monto_sobrefactura,
            "n_infladas": len(infladas),
        })

    out_dir = control_path.parent

    # Sort by monto_objetable desc
    criticos.sort(key=lambda c: -c["monto_objetable"])

    total_objetable = sum(c["monto_objetable"] for c in criticos)
    total_duplicado = sum(c["monto_duplicado"] for c in criticos)
    total_sobrefactura = sum(c["monto_sobrefactura"] for c in criticos)
    total_facturas_infladas = sum(c["n_infladas"] for c in criticos)

    # CSV
    csv_path = out_dir / "informe_criticos.csv"
    with csv_path.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow([
            "Remision_No", "Valor_remision_real",
            "Factura_legitima", "Fecha_legitima", "Bote_legitima", "Valor_factura_legitima",
            "Factura_inflada", "Fecha_inflada", "Bote_inflada", "Valor_factura_inflada",
            "Monto_duplicado", "Monto_sobrefactura", "Monto_objetable_total",
            "Path_factura_inflada", "Path_remision_inflada",
        ])
        for c in criticos:
            leg = c["legitimas"][0]  # primera legitima como referencia
            for inf in c["infladas"]:
                path_fac = facturas_dir / f"FC{inf['numdoctra']}" / f"FAC-FC{inf['numdoctra']}.pdf"
                path_rem = facturas_dir / f"FC{inf['numdoctra']}" / inf.get("archivo", "")
                w.writerow([
                    c["rno"], c["valor_remision_real"],
                    f"FC{leg['numdoctra']}", str(leg.get("fecha_factura") or "")[:10],
                    leg.get("bote") or "", leg.get("valor_factura") or "",
                    f"FC{inf['numdoctra']}", str(inf.get("fecha_factura") or "")[:10],
                    inf.get("bote") or "", inf.get("valor_factura") or "",
                    c["valor_remision_real"],
                    inf["valor_factura"] - c["valor_remision_real"],
                    inf["valor_factura"],
                    str(path_fac), str(path_rem),
                ])

    # MD para contadora de Todomar
    md_path = out_dir / "INFORME_CRITICOS.md"
    L = []
    L.append("# Informe Forense de Cobros Objetables")
    L.append("## Remisiones reutilizadas como soporte de facturas infladas")
    L.append("")
    L.append("**De:** Nautiturismo SAS (NIT 901.459.048)")
    L.append("**Para:** Departamento de Contabilidad — Todomar CHL S.A.S. (NIT 806.003.144)")
    L.append(f"**Fecha del informe:** {datetime.now().strftime('%d/%m/%Y')}")
    L.append("")
    L.append("## 1. Resumen ejecutivo")
    L.append("")
    L.append("En el proceso de conciliación de las facturas de combustible emitidas por Todomar")
    L.append("a Nautiturismo en el periodo analizado, identificamos un patrón sistemático de")
    L.append("**reutilización de números de remisión como soporte de facturas infladas**:")
    L.append("")
    L.append("Para una misma Remisión No. (un único despacho físico real), encontramos:")
    L.append("- **Una factura LEGÍTIMA** donde el valor facturado coincide con el valor del despacho")
    L.append("  documentado en la remisión.")
    L.append("- **Una o más facturas INFLADAS** donde se adjunta como soporte la MISMA remisión,")
    L.append("  pero el valor facturado es significativamente mayor al despacho real.")
    L.append("")
    L.append("Estas facturas infladas son **totalmente objetables** porque:")
    L.append("- El despacho documentado en su remisión-soporte ya fue facturado en otra factura legítima")
    L.append("- La diferencia entre lo facturado y la remisión NO tiene NINGÚN respaldo documental")
    L.append("")
    L.append("### Cifras consolidadas")
    L.append("")
    L.append("| Concepto | Valor |")
    L.append("|---|---:|")
    L.append(f"| Casos críticos detectados | **{len(criticos)}** |")
    L.append(f"| Facturas infladas (objetables) | **{total_facturas_infladas}** |")
    L.append(f"| Monto duplicado (remisiones ya cobradas) | ${total_duplicado:,.0f} |")
    L.append(f"| Sobrefactura sin soporte documental | ${total_sobrefactura:,.0f} |")
    L.append(f"| **MONTO TOTAL OBJETABLE (a reembolsar)** | **${total_objetable:,.0f}** |")
    L.append("")
    L.append("Se solicita la emisión de nota crédito por **${:,.0f}** correspondiente al valor".format(total_objetable))
    L.append("total de las facturas infladas listadas a continuación.")
    L.append("")
    L.append("---")
    L.append("")

    if not criticos:
        L.append("## ✅ No se detectaron casos críticos")
        L.append("")
        L.append("Tras el análisis cruzado entre la hoja Detalle Remisiones y la hoja Conciliación")
        L.append("del archivo de control, **no se encontraron casos donde una misma remisión soporte")
        L.append("una factura legítima y simultáneamente una factura inflada**.")
        L.append("")
        L.append("Los duplicados de número de remisión detectados se explican por reuso de consecutivo")
        L.append(f"por cambio de sistema (gap temporal > {gap_sistema_dias} días entre apariciones).")
    else:
        L.append("## 2. Detalle caso por caso")
        L.append("")
        for idx, c in enumerate(criticos, start=1):
            rno = c["rno"]
            leg = c["legitimas"][0]
            L.append(f"### Caso {idx}: Remisión No. **{rno}** — Despacho real: ${c['valor_remision_real']:,.0f}")
            L.append("")

            # Factura legítima (referencia)
            L.append("**✅ Factura LEGÍTIMA (referencia del despacho real):**")
            L.append("")
            L.append("| Factura | Fecha | Bote | Valor facturado | Valor remisión | Estado |")
            L.append("|---|---|---|---:|---:|---|")
            fecha_str = str(leg.get("fecha_factura") or "")[:10]
            vf = leg.get("valor_factura") or 0
            vr = leg.get("valor_remision_det") or 0
            L.append(f"| **FC{leg['numdoctra']}** | {fecha_str} | {leg.get('bote') or '—'} | "
                     f"${vf:,.0f} | ${vr:,.0f} | ✓ Cuadra |")
            L.append("")

            # Facturas infladas (objetables)
            L.append(f"**❌ Factura{'s' if len(c['infladas']) > 1 else ''} INFLADA{'S' if len(c['infladas']) > 1 else ''} (objetable{'s' if len(c['infladas']) > 1 else ''}):**")
            L.append("")
            L.append("| Factura | Fecha | Bote | Valor facturado | Valor real (remisión) | Sobrefactura |")
            L.append("|---|---|---|---:|---:|---:|")
            for inf in c["infladas"]:
                fecha_str = str(inf.get("fecha_factura") or "")[:10]
                vfi = inf["valor_factura"]
                sobref = vfi - c["valor_remision_real"]
                L.append(f"| **FC{inf['numdoctra']}** | {fecha_str} | {inf.get('bote') or '—'} | "
                         f"${vfi:,.0f} | ${c['valor_remision_real']:,.0f} | +${sobref:,.0f} |")
            L.append("")

            L.append(f"**Argumentación del caso {idx}:**")
            L.append("")
            L.append(f"- La Remisión No. {rno} documenta un despacho real por ${c['valor_remision_real']:,.0f}, "
                     f"correctamente facturado en su factura **FC{leg['numdoctra']}**.")
            for inf in c["infladas"]:
                L.append(f"- En la factura **FC{inf['numdoctra']}** (${inf['valor_factura']:,.0f}), "
                         f"ustedes adjuntaron como soporte la **MISMA Remisión No. {rno}** (${c['valor_remision_real']:,.0f}), "
                         f"lo cual implica una duplicación del cobro del despacho documentado.")
                L.append(f"  Adicionalmente, la diferencia de **${inf['valor_factura'] - c['valor_remision_real']:,.0f}** "
                         f"entre lo facturado y el valor de la remisión no cuenta con ningún soporte documental adicional.")
            L.append(f"- En consecuencia, la(s) factura(s) inflada(s) son **totalmente objetable(s)** "
                     f"por un monto total de **${sum(i['valor_factura'] for i in c['infladas']):,.0f}**.")
            L.append("")

            L.append(f"**Evidencia documental (archivos en G:\\):**")
            L.append("")
            L.append(f"- Factura legítima FC{leg['numdoctra']}: `G:\\Mi unidad\\...\\Facturas\\FC{leg['numdoctra']}\\FAC-FC{leg['numdoctra']}.pdf` "
                     f"+ remisión soporte `{leg.get('archivo', '')}`")
            for inf in c["infladas"]:
                L.append(f"- Factura inflada FC{inf['numdoctra']}: `G:\\Mi unidad\\...\\Facturas\\FC{inf['numdoctra']}\\FAC-FC{inf['numdoctra']}.pdf` "
                         f"+ remisión soporte (duplicada) `{inf.get('archivo', '')}`")
            L.append("")
            L.append("---")
            L.append("")

        L.append("## 3. Solicitud formal")
        L.append("")
        L.append(f"Con base en la evidencia documental anterior, **solicitamos formalmente** a Todomar CHL S.A.S.:")
        L.append("")
        L.append(f"1. La **emisión de nota crédito por valor total de ${total_objetable:,.0f}**, correspondiente")
        L.append(f"   al monto íntegro de las {total_facturas_infladas} factura(s) inflada(s) listada(s),")
        L.append(f"   las cuales reutilizan remisiones ya legítimamente facturadas y carecen de soporte propio.")
        L.append("")
        L.append("2. Una **explicación formal** sobre el proceso interno que permitió la reutilización de números")
        L.append("   de remisión como soporte de facturas distintas.")
        L.append("")
        L.append("3. La **implementación de controles** que impidan que un mismo número de remisión sea")
        L.append("   adjuntado como soporte de más de una factura.")
        L.append("")
        L.append("4. Una **auditoría conjunta** del periodo no analizado en este informe, para verificar")
        L.append("   si el patrón se repite en otras facturas.")
        L.append("")
        L.append("## 4. Anexos")
        L.append("")
        L.append(f"- `INFORME_CRITICOS.md` — este documento")
        L.append(f"- `informe_criticos.csv` — datos en formato tabular para análisis")
        L.append(f"- PDFs originales de las {total_facturas_infladas + len(criticos)} facturas y sus remisiones soporte")
        L.append("  (rutas indicadas en cada caso)")
        L.append("")
        L.append("Quedamos atentos a su pronta respuesta para concertar reunión y dar seguimiento.")
        L.append("")
        L.append("Cordialmente,")
        L.append("")
        L.append("Francisco Cortázar  ")
        L.append("Nautiturismo SAS  ")
        L.append("NIT 901.459.048")

    md_path.write_text("\n".join(L), encoding="utf-8")

    # Consola
    print("\n" + "=" * 72)
    print("  INFORME CRÍTICOS — Remisiones duplicadas + Sobrefactura")
    print("=" * 72)
    print(f"  Casos críticos detectados:           {len(criticos)}")
    print(f"  Facturas infladas (objetables):      {total_facturas_infladas}")
    print(f"  Monto duplicado:                     ${total_duplicado:>14,.0f}")
    print(f"  Sobrefactura sin soporte:            ${total_sobrefactura:>14,.0f}")
    print("  " + "-" * 64)
    print(f"  💰 MONTO TOTAL OBJETABLE:            ${total_objetable:>14,.0f}")
    print("=" * 72)
    print(f"\n  Archivos generados en: {out_dir}")
    print(f"    • {csv_path.name}")
    print(f"    • {md_path.name}  ← informe para contadora Todomar")
    print("=" * 72)

    if criticos:
        print(f"\n  TOP 5 casos por monto objetable:")
        for c in criticos[:5]:
            print(f"    Remisión #{c['rno']:>8}  →  Legítima FC{c['legitimas'][0]['numdoctra']} "
                  f"+ {c['n_infladas']} inflada(s)  →  ${c['monto_objetable']:>12,.0f}")

    log.info("informe_criticos_done",
             casos_criticos=len(criticos),
             facturas_infladas=total_facturas_infladas,
             monto_objetable=total_objetable,
             monto_duplicado=total_duplicado,
             monto_sobrefactura=total_sobrefactura)


def generar_informe(control_path: Path, log: RunLog) -> None:
    """Genera 4 CSVs y un Markdown con todo lo necesario para el informe a Todomar.

    Lee el Excel Conciliacion y agrupa por categoria:
    1. Diferencias  (col K contiene 'diferente'; usa signo de col L para a-favor-de)
    2. Sin remision (col K contiene 'No hay remisión')
    3. Sin correo   (col P contiene 'No se encontró')
    4. Pendiente revision manual (col K contiene 'Pendiente')

    Genera en la carpeta Control/:
      - informe_diferencias.csv
      - informe_sin_remision.csv
      - informe_sin_factura.csv
      - informe_pendiente_revision.csv
      - INFORME_RESUMEN.md (Markdown listo para email)
    """
    import csv

    wb = load_workbook(str(control_path), data_only=True)
    ws = wb["Conciliación"]

    diferencias_pos = []  # factura > remision -> a favor Nautiturismo
    diferencias_neg = []  # factura < remision -> a favor Todomar
    sin_remision = []
    sin_factura = []
    pendiente = []

    for r in range(2, ws.max_row + 1):
        numdoctra = ws.cell(row=r, column=COL["NUMDOCTRA"]).value
        if numdoctra is None:
            continue
        fecha = ws.cell(row=r, column=COL["Fecha factura"]).value
        bote = ws.cell(row=r, column=COL["Nombre de Bote"]).value
        v_factura = ws.cell(row=r, column=COL["Valor factura"]).value
        v_remision = ws.cell(row=r, column=COL["Valor remisión"]).value
        n_remisiones = ws.cell(row=r, column=COL["# Remisiones"]).value
        conc = ws.cell(row=r, column=COL["Conciliación"]).value or ""
        v_diff = ws.cell(row=r, column=COL["Valor (diferencia)"]).value
        obs = ws.cell(row=r, column=COL["Observaciones"]).value or ""

        num_str = str(int(numdoctra) if isinstance(numdoctra, float) else numdoctra).strip()
        fecha_str = str(fecha)[:10] if fecha else ""

        if "diferente" in conc.lower():
            row = {
                "NUMDOCTRA": num_str, "Fecha": fecha_str, "Bote": bote or "",
                "V_factura": v_factura, "V_remision": v_remision,
                "N_remisiones": n_remisiones, "Diferencia": v_diff,
                "Observaciones": obs,
            }
            if isinstance(v_diff, (int, float)) and v_diff > 0:
                diferencias_pos.append(row)
            else:
                diferencias_neg.append(row)
        elif "no hay remisi" in conc.lower():
            sin_remision.append({
                "NUMDOCTRA": num_str, "Fecha": fecha_str,
                "V_factura": v_factura, "Observaciones": obs,
            })
        elif "pendiente" in conc.lower():
            pendiente.append({
                "NUMDOCTRA": num_str, "Fecha": fecha_str, "Bote": bote or "",
                "V_factura": v_factura, "V_remision": v_remision,
                "N_remisiones": n_remisiones, "Observaciones": obs,
            })
        elif "no se encontró" in obs.lower() or "no se encontro" in obs.lower():
            sin_factura.append({
                "NUMDOCTRA": num_str, "Fecha": fecha_str, "V_factura": v_factura,
            })

    out_dir = control_path.parent

    def _write_csv(fname: str, rows: list[dict], headers: list[str]) -> Path:
        path = out_dir / fname
        with path.open("w", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=headers)
            w.writeheader()
            for row in rows:
                w.writerow(row)
        return path

    # CSVs
    p_dif_pos = _write_csv("informe_diferencias_a_favor_Nautiturismo.csv", diferencias_pos,
                           ["NUMDOCTRA", "Fecha", "Bote", "V_factura", "V_remision",
                            "N_remisiones", "Diferencia", "Observaciones"])
    p_dif_neg = _write_csv("informe_diferencias_a_favor_Todomar.csv", diferencias_neg,
                           ["NUMDOCTRA", "Fecha", "Bote", "V_factura", "V_remision",
                            "N_remisiones", "Diferencia", "Observaciones"])
    p_sin_rem = _write_csv("informe_sin_remision.csv", sin_remision,
                           ["NUMDOCTRA", "Fecha", "V_factura", "Observaciones"])
    p_sin_fac = _write_csv("informe_sin_factura.csv", sin_factura,
                           ["NUMDOCTRA", "Fecha", "V_factura"])
    p_pendiente = _write_csv("informe_pendiente_revision.csv", pendiente,
                             ["NUMDOCTRA", "Fecha", "Bote", "V_factura", "V_remision",
                              "N_remisiones", "Observaciones"])

    # Totales
    def _sum(rows: list[dict], key: str) -> float:
        return sum(r.get(key, 0) for r in rows
                   if isinstance(r.get(key), (int, float)))

    total_pos_diff = _sum(diferencias_pos, "Diferencia")
    total_neg_diff = abs(_sum(diferencias_neg, "Diferencia"))
    total_sin_rem = _sum(sin_remision, "V_factura")
    total_sin_fac = _sum(sin_factura, "V_factura")
    total_pendiente = _sum(pendiente, "V_factura")
    total_expuesto = total_sin_rem + total_sin_fac + total_pendiente

    # Markdown ready-to-email
    md_path = out_dir / "INFORME_RESUMEN.md"
    md_lines = []
    md_lines.append("# Informe de Conciliación – Facturas Combustible")
    md_lines.append("")
    md_lines.append("**De:** Nautiturismo SAS (NIT 901.459.048)")
    md_lines.append("**Para:** Todomar CHL S.A.S. (NIT 806.003.144)")
    md_lines.append(f"**Fecha del informe:** {datetime.now().strftime('%d/%m/%Y')}")
    md_lines.append("")
    md_lines.append("## Resumen ejecutivo")
    md_lines.append("")
    md_lines.append(f"| Categoría | Cantidad | Total ($) |")
    md_lines.append(f"|---|---:|---:|")
    md_lines.append(f"| 🔴 Diferencias a favor de Nautiturismo | {len(diferencias_pos)} | ${total_pos_diff:,.0f} |")
    md_lines.append(f"| 🔴 Diferencias a favor de Todomar | {len(diferencias_neg)} | ${total_neg_diff:,.0f} |")
    md_lines.append(f"| 🟡 Facturas sin remisión adjunta | {len(sin_remision)} | ${total_sin_rem:,.0f} |")
    md_lines.append(f"| 🟠 Facturas pendiente revisión manual | {len(pendiente)} | ${total_pendiente:,.0f} |")
    md_lines.append(f"| 📭 Facturas sin correo recibido | {len(sin_factura)} | ${total_sin_fac:,.0f} |")
    md_lines.append(f"| **⚠ TOTAL EXPUESTO (sin evidencia válida)** | **{len(sin_remision)+len(sin_factura)+len(pendiente)}** | **${total_expuesto:,.0f}** |")
    md_lines.append("")
    md_lines.append(f"**Saldo neto a favor de Nautiturismo (a reclamar):** ${total_pos_diff - total_neg_diff:,.0f}")
    md_lines.append("")

    # Sección 1: sin remisión
    if sin_remision:
        md_lines.append("## 1. Facturas sin remisión adjunta")
        md_lines.append("")
        md_lines.append("Las siguientes facturas llegaron vía Facture sin la remisión correspondiente. **Solicitamos comedidamente el envío de las remisiones para soportar el despacho.**")
        md_lines.append("")
        md_lines.append("| NUMDOCTRA | Fecha | Valor facturado |")
        md_lines.append("|---|---|---:|")
        for r in sin_remision:
            v = r["V_factura"] if isinstance(r["V_factura"], (int, float)) else 0
            md_lines.append(f"| FC{r['NUMDOCTRA']} | {r['Fecha']} | ${v:,.0f} |")
        md_lines.append(f"| **TOTAL** | | **${total_sin_rem:,.0f}** |")
        md_lines.append("")

    # Sección 2: sin factura
    if sin_factura:
        md_lines.append("## 2. Facturas sin correo recibido (sin evidencia documental)")
        md_lines.append("")
        md_lines.append("Las siguientes facturas aparecen en el estado de cuenta de Todomar pero **no se recibieron vía Facture en nuestra bandeja**. Solicitamos el reenvío de cada una con su respectiva remisión.")
        md_lines.append("")
        md_lines.append(f"Total facturas afectadas: **{len(sin_factura)}** por valor de **${total_sin_fac:,.0f}**.")
        md_lines.append("")
        md_lines.append("*(Ver listado completo en `informe_sin_factura.csv`)*")
        md_lines.append("")

    # Sección 3: diferencias a favor de Nautiturismo
    if diferencias_pos:
        md_lines.append("## 3. Diferencias a favor de Nautiturismo (Todomar cobró de más)")
        md_lines.append("")
        md_lines.append(f"En las siguientes **{len(diferencias_pos)} facturas** el valor facturado supera al valor del despacho registrado en la remisión, generando un saldo a favor de Nautiturismo por un total de **${total_pos_diff:,.0f}**.")
        md_lines.append("")
        md_lines.append("Solicitamos la emisión de la nota crédito correspondiente.")
        md_lines.append("")
        md_lines.append("| NUMDOCTRA | Bote | Fecha | V. factura | V. remisión | Diferencia | # Rem |")
        md_lines.append("|---|---|---|---:|---:|---:|---:|")
        for r in diferencias_pos[:30]:  # primeras 30 en el MD; el CSV tiene todas
            vf = r["V_factura"] if isinstance(r["V_factura"], (int, float)) else 0
            vr = r["V_remision"] if isinstance(r["V_remision"], (int, float)) else 0
            df = r["Diferencia"] if isinstance(r["Diferencia"], (int, float)) else 0
            md_lines.append(f"| FC{r['NUMDOCTRA']} | {r['Bote']} | {r['Fecha']} | ${vf:,.0f} | ${vr:,.0f} | +${df:,.0f} | {r['N_remisiones']} |")
        if len(diferencias_pos) > 30:
            md_lines.append(f"| ... y {len(diferencias_pos)-30} más | | | | | | |")
        md_lines.append(f"| **TOTAL** | | | | | **${total_pos_diff:,.0f}** | |")
        md_lines.append("")
        md_lines.append("*(Detalle completo en `informe_diferencias_a_favor_Nautiturismo.csv`)*")
        md_lines.append("")

    # Sección 4: diferencias a favor de Todomar (transparencia)
    if diferencias_neg:
        md_lines.append("## 4. Diferencias a favor de Todomar (por transparencia)")
        md_lines.append("")
        md_lines.append(f"Por transparencia, también listamos {len(diferencias_neg)} facturas donde el despacho registrado en la remisión supera al valor facturado (Todomar despachó más combustible del que facturó), por un total de **${total_neg_diff:,.0f}**.")
        md_lines.append("")
        md_lines.append("*(Detalle en `informe_diferencias_a_favor_Todomar.csv`)*")
        md_lines.append("")

    # Sección 5: pendiente revisión manual
    if pendiente:
        md_lines.append("## 5. Pendiente revisión manual")
        md_lines.append("")
        md_lines.append(f"Las siguientes **{len(pendiente)} facturas** tienen remisión adjunta pero el valor no se pudo extraer automáticamente (imagen ilegible). Nautiturismo está revisando estas manualmente.")
        md_lines.append("")
        md_lines.append("*(Listado en `informe_pendiente_revision.csv`)*")
        md_lines.append("")

    md_lines.append("---")
    md_lines.append("")
    md_lines.append("Quedamos atentos a su pronta respuesta para cerrar el proceso de conciliación.")
    md_lines.append("")
    md_lines.append("Cordialmente,")
    md_lines.append("")
    md_lines.append("Francisco Cortázar  ")
    md_lines.append("Nautiturismo SAS  ")
    md_lines.append("NIT 901.459.048")

    md_path.write_text("\n".join(md_lines), encoding="utf-8")

    # Console summary
    print("\n" + "=" * 70)
    print("  INFORME GENERADO")
    print("=" * 70)
    print(f"  🔴 Diferencias a favor Nautiturismo: {len(diferencias_pos):>4}  ${total_pos_diff:>14,.0f}")
    print(f"  🔴 Diferencias a favor Todomar:      {len(diferencias_neg):>4}  ${total_neg_diff:>14,.0f}")
    print(f"  🟡 Sin remisión adjunta:             {len(sin_remision):>4}  ${total_sin_rem:>14,.0f}")
    print(f"  🟠 Pendiente revisión manual:        {len(pendiente):>4}  ${total_pendiente:>14,.0f}")
    print(f"  📭 Sin correo recibido:              {len(sin_factura):>4}  ${total_sin_fac:>14,.0f}")
    print("  " + "-" * 60)
    print(f"  ⚠ TOTAL EXPUESTO (sin evidencia):   {len(sin_remision)+len(sin_factura)+len(pendiente):>4}  ${total_expuesto:>14,.0f}")
    print(f"  💰 NETO A RECLAMAR a Todomar:        {'':>4}  ${total_pos_diff - total_neg_diff:>14,.0f}")
    print("=" * 70)
    print(f"\n  Archivos generados en: {out_dir}")
    print(f"    • {p_dif_pos.name}")
    print(f"    • {p_dif_neg.name}")
    print(f"    • {p_sin_rem.name}")
    print(f"    • {p_sin_fac.name}")
    print(f"    • {p_pendiente.name}")
    print(f"    • {md_path.name}  ← copiar/pegar al email")
    print("=" * 70)

    log.info("informe_generado",
             diferencias_pos=len(diferencias_pos), diferencias_neg=len(diferencias_neg),
             sin_remision=len(sin_remision), sin_factura=len(sin_factura),
             pendiente=len(pendiente), total_expuesto=total_expuesto,
             neto_reclamar=total_pos_diff - total_neg_diff)


def mark_missing_facturas(control_path: Path, log: RunLog) -> int:
    """Marca en col Observaciones las facturas del control que NO tienen correo
    recibido (col K Conciliacion vacia). Util para identificar visualmente las
    facturas sin email para reclamar a Nautiturismo.

    Si la celda Observaciones ya tiene algo (no vacia), no la sobrescribe.

    Retorna cuantas se marcaron.
    """
    wb = load_workbook(str(control_path))
    ws = wb["Conciliación"]
    _ensure_observaciones_header(ws)

    marked = 0
    for r in range(2, ws.max_row + 1):
        numdoctra = ws.cell(row=r, column=COL["NUMDOCTRA"]).value
        if numdoctra is None:
            continue
        conciliacion = ws.cell(row=r, column=COL["Conciliación"]).value
        if conciliacion:
            continue  # ya conciliada, no es faltante
        obs_cell = ws.cell(row=r, column=COL["Observaciones"])
        if obs_cell.value:
            continue  # ya tiene observacion (no pisar)
        obs_cell.value = "No se encontró factura"
        marked += 1

    wb.save(str(control_path))
    log.info("missing_marked", count=marked)

    # Actualizar el desglose mensual de faltantes en la hoja Resumen
    update_faltantes_breakdown_in_resumen(control_path, log)
    return marked


def agregar_hallazgos_a_resumen(control_path: Path, facturas_dir: Path,
                                 tolerance: float, log: RunLog) -> None:
    """Agrega al final de la hoja Resumen una seccion con HALLAZGOS FORENSES:
    - Casos criticos (remision duplicada + sobrefactura)
    - Diferencias a favor Nautiturismo vs Todomar
    - Detalles por patron sospechoso
    - Total objetable consolidado para reclamacion
    """
    from collections import defaultdict

    wb = load_workbook(str(control_path))
    if "Resumen" not in wb.sheetnames or "Conciliación" not in wb.sheetnames:
        wb.close()
        return

    # === Leer datos ===
    cons_ws = wb["Conciliación"]
    cons_index: dict = {}
    for r in range(2, cons_ws.max_row + 1):
        n = cons_ws.cell(row=r, column=COL["NUMDOCTRA"]).value
        if n is None:
            continue
        num_str = str(int(n) if isinstance(n, float) else n).strip()
        cons_index[num_str] = {
            "fecha_factura": cons_ws.cell(row=r, column=COL["Fecha factura"]).value,
            "bote": cons_ws.cell(row=r, column=COL["Nombre de Bote"]).value,
            "valor_factura": cons_ws.cell(row=r, column=COL["Valor factura"]).value,
            "valor_remision": cons_ws.cell(row=r, column=COL["Valor remisión"]).value,
            "conciliacion": cons_ws.cell(row=r, column=COL["Conciliación"]).value or "",
            "diferencia": cons_ws.cell(row=r, column=COL["Valor (diferencia)"]).value,
            "observaciones": cons_ws.cell(row=r, column=COL["Observaciones"]).value or "",
        }

    # === Detectar casos criticos (mismo algoritmo que --informe-criticos) ===
    criticos = []
    nums_en_criticos = set()
    if "Detalle Remisiones" in wb.sheetnames:
        det_ws = wb["Detalle Remisiones"]
        by_rno: dict = defaultdict(list)
        for r in range(2, det_ws.max_row + 1):
            numdoctra = det_ws.cell(row=r, column=DETALLE_COL["NUMDOCTRA Factura"]).value
            rno = det_ws.cell(row=r, column=DETALLE_COL["Remisión No."]).value
            if numdoctra is None or rno is None:
                continue
            num_str = str(int(numdoctra) if isinstance(numdoctra, float) else numdoctra).strip()
            by_rno[str(rno).strip()].append({
                "numdoctra": num_str,
                "valor_remision_det": det_ws.cell(row=r, column=DETALLE_COL["Valor remisión"]).value,
            })
        gap_max = int(os.environ.get("CONCILIADOR_GAP_SISTEMA_DIAS", "365"))
        for rno, occs in by_rno.items():
            if len(set(o["numdoctra"] for o in occs)) < 2:
                continue
            fechas = []
            for o in occs:
                cd = cons_index.get(o["numdoctra"], {})
                f = _parse_fecha_safe(cd.get("fecha_factura"))
                if f:
                    fechas.append(f)
            if len(fechas) >= 2 and (max(fechas) - min(fechas)).days > gap_max:
                continue
            legitimas, infladas = [], []
            for o in occs:
                cd = cons_index.get(o["numdoctra"], {})
                vf = cd.get("valor_factura")
                vrd = o.get("valor_remision_det")
                if not isinstance(vf, (int, float)) or not isinstance(vrd, (int, float)):
                    continue
                if abs(vf - vrd) <= tolerance:
                    legitimas.append({**o, **cd})
                elif vf > vrd + tolerance:
                    infladas.append({**o, **cd})
            if legitimas and infladas:
                for inf in infladas:
                    nums_en_criticos.add(inf["numdoctra"])
                criticos.append({
                    "monto_objetable": sum(i["valor_factura"] for i in infladas),
                    "n_infladas": len(infladas),
                })

    # === Diferencias simples (excluyendo criticos) ===
    diff_pos = 0.0  # a favor Nautiturismo (factura > remision)
    diff_neg = 0.0  # a favor Todomar (factura < remision)
    n_diff_pos = n_diff_neg = 0
    consolidadas_n = consolidadas_monto = 0
    diff_recurrente_n = diff_recurrente_monto = 0
    sin_remision_n = sin_remision_monto = 0
    sin_correo_n = sin_correo_monto = 0
    pendiente_n = pendiente_monto = 0

    diff_counts: dict = defaultdict(int)
    for num, d in cons_index.items():
        if num in nums_en_criticos:
            continue
        if "diferente" in d["conciliacion"].lower():
            df = d.get("diferencia")
            if isinstance(df, (int, float)) and df > 0:
                diff_counts[round(df)] += 1

    for num, d in cons_index.items():
        if num in nums_en_criticos:
            continue
        conc = d["conciliacion"].lower()
        obs = d["observaciones"].lower()
        vf = d.get("valor_factura") if isinstance(d.get("valor_factura"), (int, float)) else 0
        df = d.get("diferencia") if isinstance(d.get("diferencia"), (int, float)) else 0
        bote = str(d.get("bote") or "")

        if "no hay remisi" in conc:
            sin_remision_n += 1
            sin_remision_monto += vf
        elif "pendiente" in conc:
            pendiente_n += 1
            pendiente_monto += vf
        elif "diferente" in conc:
            if df > 0:
                n_diff_pos += 1
                diff_pos += df
                if "," in bote:
                    consolidadas_n += 1
                    consolidadas_monto += df
                if diff_counts.get(round(df), 0) >= 3:
                    diff_recurrente_n += 1
                    diff_recurrente_monto += df
            elif df < 0:
                n_diff_neg += 1
                diff_neg += abs(df)
        elif "no se encontró" in obs or "no se encontro" in obs:
            sin_correo_n += 1
            sin_correo_monto += vf

    total_criticos_monto = sum(c["monto_objetable"] for c in criticos)
    total_criticos_facturas = sum(c["n_infladas"] for c in criticos)

    # === Escribir en Resumen ===
    res = wb["Resumen"]
    # Encontrar la siguiente fila libre despues del desglose mensual
    start_row = max(res.max_row, 33) + 4

    section_font = Font(bold=True, size=13, color="FFFFFF")
    section_fill = PatternFill("solid", fgColor="305496")
    bold_font = Font(bold=True, size=11)
    money_font = Font(bold=True, size=12, color="1F4E79")
    total_font_local = Font(bold=True, size=14, color="9C0006")
    centered = Alignment(horizontal="center", vertical="center")
    left_aligned = Alignment(horizontal="left", vertical="center", indent=1)
    right_aligned = Alignment(horizontal="right", vertical="center", indent=1)
    fill_rojo = PatternFill("solid", fgColor="FCE4E4")
    fill_amarillo = PatternFill("solid", fgColor="FFF2CC")
    fill_naranja = PatternFill("solid", fgColor="FCE6C9")

    # Header de seccion
    res.merge_cells(start_row=start_row, start_column=1, end_row=start_row, end_column=4)
    res.cell(row=start_row, column=1, value="🔎 HALLAZGOS FORENSES — RESUMEN PARA RECLAMACIÓN")
    res.cell(row=start_row, column=1).font = section_font
    res.cell(row=start_row, column=1).fill = section_fill
    res.cell(row=start_row, column=1).alignment = centered
    res.row_dimensions[start_row].height = 24

    # Tabla
    headers = ["Categoría", "Facturas", "Monto", "Acción"]
    r = start_row + 2
    for i, h in enumerate(headers, 1):
        c = res.cell(row=r, column=i, value=h)
        c.font = bold_font
        c.fill = PatternFill("solid", fgColor="D9E1F2")
        c.alignment = centered
        c.border = THIN_BORDER
    r += 1

    rows_data = [
        ("🔴 Casos críticos (remisión duplicada + sobrefactura)",
         total_criticos_facturas, total_criticos_monto,
         "Reclamar nota crédito por monto íntegro", fill_rojo),
        ("🔴 Diferencias a favor Nautiturismo (Todomar cobró de más)",
         n_diff_pos, diff_pos,
         "Reclamar nota crédito por la diferencia", fill_rojo),
        ("🟠 Diferencias a favor Todomar (despacharon de más)",
         n_diff_neg, diff_neg,
         "Por transparencia, mencionar en informe", fill_naranja),
        ("🟡 Facturas sin remisión adjunta",
         sin_remision_n, sin_remision_monto,
         "Solicitar reenvío de remisiones", fill_amarillo),
        ("🟠 Facturas pendiente revisión manual",
         pendiente_n, pendiente_monto,
         "Verificar PDF y completar manual", fill_naranja),
        ("📭 Facturas sin correo recibido",
         sin_correo_n, sin_correo_monto,
         "Solicitar reenvío de factura completa", fill_amarillo),
    ]
    for label, cant, monto, accion, fill in rows_data:
        res.cell(row=r, column=1, value=label).alignment = left_aligned
        res.cell(row=r, column=2, value=cant).alignment = centered
        cmonto = res.cell(row=r, column=3, value=monto)
        cmonto.number_format = MONEY_FMT
        cmonto.font = money_font
        cmonto.alignment = right_aligned
        res.cell(row=r, column=4, value=accion).alignment = left_aligned
        for col_idx in range(1, 5):
            res.cell(row=r, column=col_idx).fill = fill
            res.cell(row=r, column=col_idx).border = THIN_BORDER
        r += 1

    # Subseccion: patrones detectados (sospechosos)
    r += 1
    res.merge_cells(start_row=r, start_column=1, end_row=r, end_column=4)
    res.cell(row=r, column=1, value="⚠ PATRONES SOSPECHOSOS DENTRO DE DIFERENCIAS (revisar antes de reclamar)")
    res.cell(row=r, column=1).font = Font(bold=True, size=11, color="9C5700")
    res.cell(row=r, column=1).fill = PatternFill("solid", fgColor="FFF2CC")
    res.cell(row=r, column=1).alignment = centered
    r += 1
    sospecha_data = [
        ("Bote consolidado (factura agrupa varios tanqueos)",
         consolidadas_n, consolidadas_monto,
         "Verificar manualmente — riesgo alto"),
        ("Diferencia idéntica recurrente (probable cargo fijo)",
         diff_recurrente_n, diff_recurrente_monto,
         "Excluir si es cargo sistemático"),
    ]
    for label, cant, monto, accion in sospecha_data:
        res.cell(row=r, column=1, value=label).alignment = left_aligned
        res.cell(row=r, column=2, value=cant).alignment = centered
        cmonto = res.cell(row=r, column=3, value=monto)
        cmonto.number_format = MONEY_FMT
        cmonto.alignment = right_aligned
        res.cell(row=r, column=4, value=accion).alignment = left_aligned
        for col_idx in range(1, 5):
            res.cell(row=r, column=col_idx).border = THIN_BORDER
            res.cell(row=r, column=col_idx).fill = PatternFill("solid", fgColor="FFF8E1")
        r += 1

    # Total consolidado a reclamar
    r += 1
    total_reclamable = total_criticos_monto + diff_pos
    total_potencial = total_reclamable + sin_remision_monto + sin_correo_monto

    res.merge_cells(start_row=r, start_column=1, end_row=r, end_column=4)
    res.cell(row=r, column=1, value="💰 TOTALES A RECLAMAR A TODOMAR")
    res.cell(row=r, column=1).font = section_font
    res.cell(row=r, column=1).fill = section_fill
    res.cell(row=r, column=1).alignment = centered
    res.row_dimensions[r].height = 24
    r += 2

    res.cell(row=r, column=1, value="✅ Total OBJETABLE DIRECTO (críticos + diferencias a favor)").font = total_font_local
    cm = res.cell(row=r, column=3, value=total_reclamable)
    cm.number_format = MONEY_FMT
    cm.font = total_font_local
    cm.alignment = right_aligned
    for col_idx in range(1, 5):
        res.cell(row=r, column=col_idx).fill = fill_rojo
        res.cell(row=r, column=col_idx).border = THIN_BORDER
    r += 1
    res.cell(row=r, column=1, value="📊 Total POTENCIAL (incl. sin remisión y sin correo)").font = bold_font
    cm = res.cell(row=r, column=3, value=total_potencial)
    cm.number_format = MONEY_FMT
    cm.font = bold_font
    cm.alignment = right_aligned
    for col_idx in range(1, 5):
        res.cell(row=r, column=col_idx).fill = fill_amarillo
        res.cell(row=r, column=col_idx).border = THIN_BORDER

    # Ajustar anchos
    res.column_dimensions["D"].width = 42

    wb.save(str(control_path))
    log.info("hallazgos_agregados_a_resumen",
             criticos=total_criticos_facturas, monto_criticos=total_criticos_monto,
             diferencias=n_diff_pos, monto_diferencias=diff_pos,
             sin_remision=sin_remision_n, total_reclamable=total_reclamable,
             total_potencial=total_potencial)


def update_faltantes_breakdown_in_resumen(control_path: Path, log: RunLog) -> None:
    """Actualiza la hoja Resumen con un desglose por mes de las facturas
    faltantes (sin correo recibido), mostrando cantidad y total facturado.

    Se escribe a partir de la fila 33 (despues de las secciones existentes).
    Si se ejecuta varias veces, sobrescribe el bloque (no acumula).
    """
    from collections import Counter

    wb = load_workbook(str(control_path))
    if "Resumen" not in wb.sheetnames or "Conciliación" not in wb.sheetnames:
        wb.close()
        return

    cons = wb["Conciliación"]

    counts_by_month: Counter = Counter()
    sum_by_month: Counter = Counter()
    for r in range(2, cons.max_row + 1):
        obs = cons.cell(row=r, column=COL["Observaciones"]).value
        if not obs or "No se encontró" not in str(obs):
            continue
        fecha = cons.cell(row=r, column=COL["Fecha factura"]).value
        valor = cons.cell(row=r, column=COL["Valor factura"]).value
        key = str(fecha)[:7] if fecha else "sin_fecha"
        counts_by_month[key] += 1
        if isinstance(valor, (int, float)):
            sum_by_month[key] += valor

    res = wb["Resumen"]

    # Borrar rows desde 33 en adelante (donde escribimos el bloque)
    if res.max_row >= 33:
        try:
            # Limpiar valores en lugar de delete_rows (mas seguro con merged cells previos)
            for r in range(33, res.max_row + 1):
                for c in range(1, 5):
                    cell = res.cell(row=r, column=c)
                    cell.value = None
                    cell.fill = PatternFill(fill_type=None)
                    cell.font = Font()
                    cell.border = Border()
                    cell.alignment = Alignment()
                    cell.number_format = "General"
        except Exception:
            pass

    if not counts_by_month:
        wb.save(str(control_path))
        return

    # Estilos consistentes con _build_resumen_sheet
    section_font = Font(bold=True, size=13, color="FFFFFF")
    section_fill = PatternFill("solid", fgColor="305496")
    header_font = Font(bold=True, size=11)
    fill_yellow = PatternFill("solid", fgColor="FFF2CC")
    fill_red = PatternFill("solid", fgColor="FCE4E4")
    centered = Alignment(horizontal="center", vertical="center")
    centered_left = Alignment(horizontal="left", vertical="center", indent=1)

    # Fila 33: header de seccion
    try:
        res.unmerge_cells("A33:D33")
    except Exception:
        pass
    res.merge_cells("A33:D33")
    res["A33"] = "📅 DESGLOSE FALTANTES POR MES (sin correo recibido)"
    res["A33"].font = section_font
    res["A33"].fill = section_fill
    res["A33"].alignment = centered
    res.row_dimensions[33].height = 22

    # Fila 35: cabeceras de la mini-tabla
    cabeceras = [("Año / Mes", 1), ("Cantidad", 2), ("Total Facturado", 3), ("Visual", 4)]
    for label, col in cabeceras:
        c = res.cell(row=35, column=col, value=label)
        c.font = header_font
        c.fill = PatternFill("solid", fgColor="D9E1F2")
        c.alignment = centered
        c.border = THIN_BORDER

    # Datos: una fila por mes
    max_count = max(counts_by_month.values()) if counts_by_month else 1
    row = 36
    for key in sorted(counts_by_month.keys()):
        cnt = counts_by_month[key]
        suma = sum_by_month.get(key, 0)
        # Barra visual proporcional (max 40 chars)
        bar_len = max(1, int(cnt / max_count * 40)) if max_count > 0 else 1
        bar = "▇" * bar_len

        res.cell(row=row, column=1, value=key).alignment = centered_left
        res.cell(row=row, column=2, value=cnt).alignment = centered
        c_val = res.cell(row=row, column=3, value=suma)
        c_val.number_format = MONEY_FMT
        c_val.alignment = Alignment(horizontal="right", vertical="center", indent=1)
        res.cell(row=row, column=4, value=bar).alignment = centered_left
        # Bordes finos
        for c in range(1, 5):
            res.cell(row=row, column=c).border = THIN_BORDER
            res.cell(row=row, column=c).fill = fill_yellow if (row % 2 == 0) else PatternFill(fill_type=None)
        row += 1

    # Fila TOTAL
    total_cnt = sum(counts_by_month.values())
    total_val = sum(sum_by_month.values())
    bold_font = Font(bold=True, size=12, color="9C0006")
    res.cell(row=row, column=1, value="TOTAL").font = bold_font
    res.cell(row=row, column=1).alignment = centered_left
    res.cell(row=row, column=2, value=total_cnt).font = bold_font
    res.cell(row=row, column=2).alignment = centered
    c_total = res.cell(row=row, column=3, value=total_val)
    c_total.font = bold_font
    c_total.number_format = MONEY_FMT
    c_total.alignment = Alignment(horizontal="right", vertical="center", indent=1)
    for c in range(1, 5):
        res.cell(row=row, column=c).fill = fill_red
        res.cell(row=row, column=c).border = THIN_BORDER

    # Ancho columna D para barras
    res.column_dimensions["D"].width = 50

    wb.save(str(control_path))
    log.info("faltantes_breakdown_updated",
             meses=len(counts_by_month), total_cant=total_cnt, total_val=total_val)


def append_log_row(control_path: Path, summary: dict) -> None:
    wb = load_workbook(str(control_path))
    ws = wb["Log"]
    next_row = ws.max_row + 1
    if next_row == 2 and ws.cell(row=2, column=1).value is None:
        next_row = 2
    ws.cell(row=next_row, column=1, value=datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    ws.cell(row=next_row, column=2, value=summary.get("emails_read", 0))
    ws.cell(row=next_row, column=3, value=summary.get("zips_downloaded", 0))
    ws.cell(row=next_row, column=4, value=summary.get("facturas_new", 0))
    ws.cell(row=next_row, column=5, value=summary.get("facturas_skipped", 0))
    ws.cell(row=next_row, column=6, value=summary.get("errors", 0))
    ws.cell(row=next_row, column=7, value=summary.get("inconsistencies", 0))
    ws.cell(row=next_row, column=8, value=summary.get("detail", ""))
    wb.save(str(control_path))


def listar_faltantes(control_path: Path, log: RunLog) -> None:
    """Lee el Excel de control y reporta las facturas sin correo recibido.

    Una factura cuenta como 'faltante' si su fila tiene la col K (Conciliacion)
    vacia, lo que significa que el script nunca proceso un correo para ese
    NUMDOCTRA.

    Genera:
      - facturas_sin_correo.csv en la carpeta Control/
      - Desglose por anio/mes en consola
    """
    import csv
    from collections import Counter

    wb = load_workbook(str(control_path), data_only=True)
    ws = wb["Conciliación"]

    faltantes: list[tuple] = []
    total_filas = 0
    procesadas = 0
    for r in range(2, ws.max_row + 1):
        numdoctra = ws.cell(row=r, column=COL["NUMDOCTRA"]).value
        if numdoctra is None:
            continue
        total_filas += 1
        conciliacion = ws.cell(row=r, column=COL["Conciliación"]).value
        if conciliacion:
            procesadas += 1
            continue
        fecha = ws.cell(row=r, column=COL["Fecha factura"]).value
        valor = ws.cell(row=r, column=COL["Valor factura"]).value
        faltantes.append((numdoctra, fecha, valor))

    # Ordenar por fecha (string YYYY/MM/DD ordena lexicograficamente bien)
    faltantes.sort(key=lambda x: (str(x[1]) if x[1] is not None else "0000/00/00", x[0]))

    # CSV
    csv_path = control_path.parent / "facturas_sin_correo.csv"
    with csv_path.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["NUMDOCTRA", "Fecha", "Valor"])
        for n, fe, va in faltantes:
            w.writerow([n, fe, va])

    # Console
    print("\n" + "=" * 60)
    print(f"  FACTURAS SIN CORREO RECIBIDO")
    print("=" * 60)
    print(f"  Total facturas en alcance (Excel):  {total_filas}")
    print(f"  Procesadas (con conciliacion):       {procesadas}")
    print(f"  Faltantes (sin correo):              {len(faltantes)}")
    print(f"\n  CSV generado: {csv_path}")

    # Desglose por anio/mes
    print(f"\n  Desglose por mes (anio/mes : cantidad):")
    months = Counter()
    valores_mes = Counter()
    for n, fe, va in faltantes:
        if fe is None:
            key = "sin_fecha"
        else:
            key = str(fe)[:7]  # YYYY/MM
        months[key] += 1
        if isinstance(va, (int, float)):
            valores_mes[key] += va

    for k in sorted(months.keys()):
        cnt = months[k]
        suma = valores_mes.get(k, 0)
        bar = "▇" * min(int(cnt / 2), 50)
        print(f"    {k}: {cnt:>4}  (${suma:>14,.0f})  {bar}")

    total_valor = sum(valores_mes.values())
    print(f"\n  Total valor de facturas faltantes: ${total_valor:,.0f}")
    print("=" * 60)

    log.info("listar_faltantes_done",
             faltantes=len(faltantes), total=total_filas, csv=str(csv_path))


# ============================================================
# Pipeline principal
# ============================================================

def process_one_email(
    cfg: dict,
    msg_id: str,
    msg: email.message.Message,
    expected_numdoctras: set[str],
    log: RunLog,
    summary: dict,
    service,
    remision_no_index: dict | None = None,
) -> None:
    subject = decode_subject(msg.get("Subject", ""))
    numdoctra = extract_numdoctra(subject)
    log.info("email", msg_id=msg_id, subject=subject, numdoctra=numdoctra)

    if not numdoctra:
        log.warn("no_numdoctra_in_subject", subject=subject)
        summary["errors"] += 1
        return

    if numdoctra not in expected_numdoctras:
        log.warn("numdoctra_not_expected", numdoctra=numdoctra)
        summary["facturas_skipped"] += 1
        return

    folder = cfg["facturas_dir"] / f"FC{numdoctra}"
    if (folder / f"FAC-FC{numdoctra}.pdf").exists():
        log.info("already_processed_skip", numdoctra=numdoctra)
        summary["facturas_skipped"] += 1
        add_label(service, msg_id, cfg["label_processed"])
        return

    attach = extract_zip_attachment(msg)
    if not attach:
        log.warn("no_zip_attachment", numdoctra=numdoctra)
        summary["errors"] += 1
        return
    zip_name, zip_bytes = attach
    summary["zips_downloaded"] += 1

    try:
        extracted = unzip_to(folder, zip_bytes)
    except zipfile.BadZipFile:
        log.error("bad_zip", numdoctra=numdoctra, zip_name=zip_name)
        summary["errors"] += 1
        return

    pdfs = [p for p in extracted if p.suffix.lower() == ".pdf"]
    if not pdfs:
        log.warn("no_pdfs_in_zip", numdoctra=numdoctra, zip_name=zip_name)
        summary["errors"] += 1
        return

    factura_path, remisiones_paths = classify_pdfs(pdfs)
    factura_path, remisiones_paths = rename_classified(folder, factura_path, remisiones_paths, numdoctra)

    if not factura_path:
        log.warn("no_factura_pdf", numdoctra=numdoctra)
        summary["errors"] += 1
        return

    factura_data = extract_factura_data(factura_path)
    if factura_data.get("nit_emisor") and cfg["nautiturismo_nit"] not in factura_data["nit_emisor"]:
        log.warn(
            "emisor_distinto",
            numdoctra=numdoctra,
            nit_found=factura_data["nit_emisor"],
        )
        target = cfg["no_aplica_dir"] / f"FC{numdoctra}"
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            shutil.rmtree(target)
        shutil.move(str(folder), str(target))
        summary["facturas_skipped"] += 1
        return

    # Cada archivo de remision retorna un dict con clave 'remisiones' (list)
    # porque un archivo puede contener varias remisiones (Vision detecta cuantas).
    remisiones_per_file = [
        extract_remision_data(p, cfg.get("anthropic_api_key"), log)
        for p in remisiones_paths
    ]

    # Aplanar para conciliacion: cada remision (incluso si estan agrupadas en
    # un mismo archivo) cuenta individualmente para sumar valores.
    # Tambien trackeamos el file_name de cada remision para el Detalle.
    all_remisiones = []
    file_name_per_remision = []
    for fd in remisiones_per_file:
        for r in fd.get("remisiones", []):
            all_remisiones.append(r)
            file_name_per_remision.append(fd.get("file_name", ""))

    if factura_data.get("valor") is None:
        log.warn("factura_value_not_extracted", numdoctra=numdoctra,
                 sample=factura_data.get("raw_text_sample"))
        summary["errors"] += 1
        return

    conc, diff = conciliate(factura_data["valor"], all_remisiones, cfg["tolerance_pesos"])
    valores_rem = [r["valor"] for r in all_remisiones if r.get("valor") is not None]

    # Construir texto de observaciones
    obs_parts = []
    for fd in remisiones_per_file:
        n_in_file = len(fd.get("remisiones", []))
        if n_in_file > 1:
            obs_parts.append(f"{fd['file_name']}: {n_in_file} remisiones consolidadas")

    # Cruzar contra lo que dice la factura ("OBSERVACIONES: N remisiones")
    n_esperadas = factura_data.get("n_remisiones_esperadas")
    n_detectadas = len(all_remisiones)
    if n_esperadas and n_esperadas != n_detectadas:
        obs_parts.append(
            f"⚠ Factura indica {n_esperadas} remisiones, se detectaron {n_detectadas}"
        )

    # Sanity check: valor sospechosamente alto (probable confusion con cedula)
    for r in all_remisiones:
        v = r.get("valor")
        if v is not None and v > VALOR_REMISION_SUSPICIOUS_THRESHOLD:
            obs_parts.append(
                f"⚠ Valor inusualmente alto (${v:,.0f}) - posible confusion con C.C./NIT - revisar manualmente"
            )

    control_path_for_write = cfg["control_dir"] / cfg["control_filename"]

    # Detalle Remisiones: borra las viejas (si reprocesando) y escribe las nuevas.
    # Detecta duplicados de Remision No. contra otras facturas.
    clear_detalle_rows_for_factura(control_path_for_write, numdoctra)
    if remision_no_index is None:
        remision_no_index = {}
    duplicate_msgs = append_detalle_remisiones(
        control_path_for_write, numdoctra, all_remisiones,
        file_name_per_remision, remision_no_index,
    )
    for dm in duplicate_msgs:
        obs_parts.append(dm)

    observaciones = " | ".join(obs_parts) if obs_parts else None

    ok = update_control_row(
        control_path_for_write,
        numdoctra, factura_data, all_remisiones, conc, diff,
        factura_path, remisiones_paths, log,
        observaciones=observaciones,
    )
    if ok:
        summary["facturas_new"] += 1
        add_label(service, msg_id, cfg["label_processed"])
        log.info(
            "conciliated",
            numdoctra=numdoctra, valor_factura=factura_data["valor"],
            valor_remision=sum(valores_rem) if valores_rem else 0,
            n_remisiones=n_detectadas, n_archivos=len(remisiones_per_file),
            n_esperadas=n_esperadas, conciliacion=conc, diferencia=diff,
            duplicados=len(duplicate_msgs),
        )


def process_one_email_no_io(
    cfg: dict,
    msg_id: str,
    msg: email.message.Message,
    expected_numdoctras: set[str],
    log: RunLog,
) -> dict:
    """Thread-safe: hace TODO el procesamiento de una factura SIN tocar Excel
    ni aplicar Gmail labels. Pensado para correr en paralelo via ThreadPoolExecutor.

    Retorna dict con 'status' indicando el resultado, y si 'status'=='to_write'
    incluye todos los datos para que write_batch_to_excel los persista.
    """
    subject = decode_subject(msg.get("Subject", ""))
    numdoctra = extract_numdoctra(subject)
    base = {"msg_id": msg_id, "subject": subject, "numdoctra": numdoctra}

    if not numdoctra:
        return {**base, "status": "skipped_no_numdoctra"}

    if numdoctra not in expected_numdoctras:
        return {**base, "status": "skipped_not_expected"}

    folder = cfg["facturas_dir"] / f"FC{numdoctra}"
    if (folder / f"FAC-FC{numdoctra}.pdf").exists():
        return {**base, "status": "already_processed"}

    attach = extract_zip_attachment(msg)
    if not attach:
        return {**base, "status": "error_no_attach"}

    zip_name, zip_bytes = attach
    try:
        extracted = unzip_to(folder, zip_bytes)
    except zipfile.BadZipFile:
        return {**base, "status": "error_bad_zip", "zip_name": zip_name}

    pdfs = [p for p in extracted if p.suffix.lower() == ".pdf"]
    if not pdfs:
        return {**base, "status": "error_no_pdfs", "zip_name": zip_name}

    factura_path, remisiones_paths = classify_pdfs(pdfs)
    factura_path, remisiones_paths = rename_classified(folder, factura_path, remisiones_paths, numdoctra)

    if not factura_path:
        return {**base, "status": "error_no_factura_pdf"}

    factura_data = extract_factura_data(factura_path)

    if factura_data.get("nit_emisor") and cfg["nautiturismo_nit"] not in factura_data["nit_emisor"]:
        target = cfg["no_aplica_dir"] / f"FC{numdoctra}"
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            shutil.rmtree(target)
        shutil.move(str(folder), str(target))
        return {**base, "status": "skipped_emisor_distinto",
                "nit_found": factura_data["nit_emisor"]}

    # Vision IO (lo mas lento — esta es la parte que paraleliza bien)
    remisiones_per_file = [
        extract_remision_data(p, cfg.get("anthropic_api_key"), log)
        for p in remisiones_paths
    ]

    all_remisiones = []
    file_name_per_remision = []
    for fd in remisiones_per_file:
        for r in fd.get("remisiones", []):
            all_remisiones.append(r)
            file_name_per_remision.append(fd.get("file_name", ""))

    if factura_data.get("valor") is None:
        return {**base, "status": "error_factura_value",
                "sample": factura_data.get("raw_text_sample")}

    conc, diff = conciliate(factura_data["valor"], all_remisiones, cfg["tolerance_pesos"])

    # Observaciones (sin duplicados aun — esos se detectan en write_batch_to_excel)
    obs_parts = []
    for fd in remisiones_per_file:
        n_in_file = len(fd.get("remisiones", []))
        if n_in_file > 1:
            obs_parts.append(f"{fd['file_name']}: {n_in_file} remisiones consolidadas")

    n_esperadas = factura_data.get("n_remisiones_esperadas")
    n_detectadas = len(all_remisiones)
    if n_esperadas and n_esperadas != n_detectadas:
        obs_parts.append(f"⚠ Factura indica {n_esperadas} remisiones, se detectaron {n_detectadas}")

    for r in all_remisiones:
        v = r.get("valor")
        if v is not None and v > VALOR_REMISION_SUSPICIOUS_THRESHOLD:
            obs_parts.append(
                f"⚠ Valor inusualmente alto (${v:,.0f}) - posible confusion con C.C./NIT - revisar manualmente"
            )

    return {
        **base,
        "status": "to_write",
        "factura_data": factura_data,
        "factura_path": factura_path,
        "remisiones_paths": remisiones_paths,
        "remisiones_per_file": remisiones_per_file,
        "all_remisiones": all_remisiones,
        "file_name_per_remision": file_name_per_remision,
        "conciliacion": conc,
        "valor_diff": diff,
        "obs_parts_before_dup": obs_parts,
        "n_esperadas": n_esperadas,
    }


def write_batch_to_excel(
    control_path: Path,
    batch: list[dict],
    remision_no_index: dict,
    cfg: dict,
    service,
    summary: dict,
    log: RunLog,
) -> None:
    """Escribe un batch de resultados al Excel en UNA sola apertura/guardado.
    Detecta duplicados de remision_no (sequencial). Aplica Gmail labels tras
    save exitoso."""
    if not batch:
        return

    wb = load_workbook(str(control_path))
    cons_ws = wb["Conciliación"]
    _ensure_observaciones_header(cons_ws)
    _ensure_detalle_sheet(wb)
    detalle_ws = wb["Detalle Remisiones"]

    successful_msg_ids: list[str] = []

    for item in batch:
        numdoctra = item["numdoctra"]
        target_str = str(numdoctra).strip()

        # 1. Borrar filas viejas de Detalle para este NUMDOCTRA
        rows_to_delete = []
        for r in range(2, detalle_ws.max_row + 1):
            v = detalle_ws.cell(row=r, column=1).value
            if v is None:
                continue
            if str(int(v) if isinstance(v, float) else v).strip() == target_str:
                rows_to_delete.append(r)
        for r in reversed(rows_to_delete):
            detalle_ws.delete_rows(r)

        # 2. Agregar nuevas filas de Detalle + detectar duplicados
        next_row = detalle_ws.max_row + 1
        if next_row == 2 and detalle_ws.cell(row=2, column=1).value is None:
            next_row = 2

        duplicate_msgs: list[str] = []
        for r, file_name in zip(item["all_remisiones"], item["file_name_per_remision"]):
            rno = r.get("remision_no")
            obs = ""
            if rno:
                rno_key = str(rno).strip()
                if rno_key in remision_no_index and remision_no_index[rno_key] != target_str:
                    msg = f"⚠ Remisión No. {rno_key} ya usada en factura FC{remision_no_index[rno_key]}"
                    obs = msg
                    duplicate_msgs.append(msg)
                else:
                    remision_no_index[rno_key] = target_str

            detalle_ws.cell(row=next_row, column=DETALLE_COL["NUMDOCTRA Factura"], value=numdoctra)
            detalle_ws.cell(row=next_row, column=DETALLE_COL["Remisión No."], value=rno)
            detalle_ws.cell(row=next_row, column=DETALLE_COL["Bote"], value=r.get("bote"))
            detalle_ws.cell(row=next_row, column=DETALLE_COL["Fecha tanqueo"], value=r.get("fecha_hora"))
            c_val = detalle_ws.cell(row=next_row, column=DETALLE_COL["Valor remisión"], value=r.get("valor"))
            if r.get("valor") is not None:
                c_val.number_format = MONEY_FMT
            detalle_ws.cell(row=next_row, column=DETALLE_COL["Archivo origen"], value=file_name)
            detalle_ws.cell(row=next_row, column=DETALLE_COL["Observaciones"], value=obs or None)
            next_row += 1

        # 3. Observaciones finales (con duplicados)
        obs_parts = list(item["obs_parts_before_dup"])
        obs_parts.extend(duplicate_msgs)
        observaciones = " | ".join(obs_parts) if obs_parts else None

        # 4. Actualizar fila de Conciliacion
        row = find_row_by_numdoctra(cons_ws, numdoctra)
        if row is None:
            log.warn("numdoctra_not_in_control", numdoctra=numdoctra)
            continue

        bote = ", ".join(filter(None, [r.get("bote") for r in item["all_remisiones"]])) or None
        fecha_h = next((r.get("fecha_hora") for r in item["all_remisiones"] if r.get("fecha_hora")), None)
        valores_extraidos = [r.get("valor") for r in item["all_remisiones"] if r.get("valor") is not None]
        suma_rem = sum(valores_extraidos) if valores_extraidos else None

        cons_ws.cell(row=row, column=COL["Nombre de Bote"], value=bote)
        cons_ws.cell(row=row, column=COL["Fecha y hora de tanqueo"], value=fecha_h)
        c_vr = cons_ws.cell(row=row, column=COL["Valor remisión"], value=suma_rem)
        if suma_rem is not None:
            c_vr.number_format = MONEY_FMT
        cons_ws.cell(row=row, column=COL["# Remisiones"], value=len(item["all_remisiones"]))
        cons_ws.cell(row=row, column=COL["Conciliación"], value=format_status_with_icon(item["conciliacion"]))
        c_diff = cons_ws.cell(row=row, column=COL["Valor (diferencia)"], value=item["valor_diff"])
        if item["valor_diff"] is not None:
            c_diff.number_format = MONEY_FMT

        c_m = cons_ws.cell(row=row, column=COL["Link factura"])
        set_hyperlink_cell(c_m, item["factura_path"],
                          item["factura_path"].name if item["factura_path"] else "")

        c_n = cons_ws.cell(row=row, column=COL["Link remisión(es)"])
        rem_links = item["remisiones_paths"]
        if not rem_links:
            c_n.value = None
        elif len(rem_links) == 1:
            set_hyperlink_cell(c_n, rem_links[0], rem_links[0].name)
        else:
            folder_path = rem_links[0].parent
            set_hyperlink_cell(c_n, folder_path, f"Carpeta ({len(rem_links)} remisiones)")

        cons_ws.cell(row=row, column=COL["Última actualización"],
                    value=datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        cons_ws.cell(row=row, column=COL["Observaciones"], value=observaciones)

        summary["facturas_new"] += 1
        successful_msg_ids.append(item["msg_id"])

        log.info("conciliated", numdoctra=numdoctra,
                 valor_factura=item["factura_data"]["valor"],
                 valor_remision=sum(valores_extraidos) if valores_extraidos else 0,
                 n_remisiones=len(item["all_remisiones"]),
                 n_archivos=len(item["remisiones_per_file"]),
                 n_esperadas=item["n_esperadas"],
                 conciliacion=item["conciliacion"],
                 diferencia=item["valor_diff"],
                 duplicados=len(duplicate_msgs))

    wb.save(str(control_path))

    # Aplicar labels Gmail despues del save exitoso
    for msg_id in successful_msg_ids:
        add_label(service, msg_id, cfg["label_processed"])

    log.info("batch_written", count=len(batch), successful=len(successful_msg_ids))


def load_expected_numdoctras(source: Path) -> set[str]:
    """Devuelve set de NUMDOCTRA esperados, leyendo desde xlsx o PDF Zeus."""
    rows = load_expected_rows(source)
    out: set[str] = set()
    for row in rows:
        v = row[0]
        if v is None:
            continue
        out.add(str(int(v) if isinstance(v, float) else v).strip())
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description="Conciliador combustible Nautiturismo->Todomar")
    parser.add_argument("--limit", type=int, default=0,
                        help="Procesar solo los N correos mas antiguos (0=todos)")
    parser.add_argument("--since", help="YYYY-MM-DD (override DATE_FROM del .env)")
    parser.add_argument("--until", help="YYYY-MM-DD (override DATE_TO del .env)")
    parser.add_argument("--dry-run", action="store_true",
                        help="No descarga, solo muestra qué se procesaría")
    parser.add_argument("--source-pdf",
                        help="Ruta a PDF Zeus de estado de cuenta (o directorio con varios PDFs). "
                             "Sobrescribe SOURCE_EXCEL del .env.")
    parser.add_argument("--validate-source", action="store_true",
                        help="Solo lee y muestra el contenido de la fuente (sin Gmail ni nada). "
                             "Util para verificar que el PDF Zeus se parsea bien.")
    parser.add_argument("--listar-faltantes", action="store_true",
                        help="Lee el Excel de control y genera CSV con facturas "
                             "que no tienen correo (cols G-O vacias). Muestra desglose por mes.")
    parser.add_argument("--marcar-faltantes", action="store_true",
                        help="Escribe 'No se encontro factura' en col Observaciones "
                             "para todas las filas sin conciliacion. Util para Excels "
                             "creados antes de que el script lo hiciera automaticamente.")
    parser.add_argument("--reprocesar-diferencias", action="store_true",
                        help="Borra las carpetas FC<num> de facturas marcadas como "
                             "'Remision con valor diferente'. Despues corres "
                             "'python conciliador.py' normalmente para reprocesarlas.")
    parser.add_argument("--detectar-duplicados", action="store_true",
                        help="Escanea la hoja Detalle Remisiones del Excel y marca "
                             "como duplicado todas las remisiones cuyo numero aparece "
                             "en mas de una factura.")
    parser.add_argument("--rebuild-resumen", action="store_true",
                        help="Borra y regenera la hoja Resumen del Excel con los "
                             "labels y formulas actuales (no toca Conciliación ni "
                             "Detalle Remisiones). Util cuando se cambian labels en codigo.")
    parser.add_argument("--informe", action="store_true",
                        help="Genera el informe consolidado para enviar a Todomar. "
                             "Crea 5 CSVs (diferencias a favor de cada uno, sin "
                             "remision, sin factura, pendiente revision) + un MD "
                             "listo para copiar/pegar al email.")
    parser.add_argument("--informe-duplicados", action="store_true",
                        help="Informe FORENSE solo de remisiones duplicadas (mismo "
                             "numero usado en 2+ facturas). Genera CSV + MD con "
                             "evidencia documental caso por caso, paths a los PDFs, "
                             "y clasificacion de la fuerza de cada caso. Ideal para "
                             "soportar reclamacion formal por cobros duplicados.")
    parser.add_argument("--informe-criticos", action="store_true",
                        help="Informe CRITICO presentable a la contadora de Todomar: "
                             "detecta remisiones reutilizadas como soporte de facturas "
                             "infladas (patron forense mas fuerte). Por cada caso, "
                             "identifica la factura legitima vs la(s) inflada(s), "
                             "calcula el monto total objetable, y arma argumentacion "
                             "formal lista para reclamacion.")
    parser.add_argument("--informe-reclamacion", action="store_true",
                        help="Informe CONSOLIDADO de reclamacion a Todomar. Combina "
                             "los 3 casos: criticos (duplicada+inflada), sin remision, "
                             "y diferencias simples. Genera MD profesional + Excel "
                             "anexo con 4 hojas, listo para presentar a la contadora.")
    parser.add_argument("--enviar-email-revision",
                        help="Envia el informe + Excel anexo por email a la(s) "
                             "direccion(es) indicada(s) (separar por coma) usando "
                             "Gmail OAuth. Asunto incluye 'BORRADOR' para indicar "
                             "que es para revision interna previa al envio a Todomar.")
    args = parser.parse_args()

    cfg = load_config()
    if args.since:
        cfg["date_from"] = args.since
    if args.until:
        cfg["date_to"] = args.until
    if args.source_pdf:
        cfg["source_excel"] = Path(args.source_pdf)  # nombre legacy, ahora puede ser PDF o dir

    cfg["facturas_dir"].mkdir(parents=True, exist_ok=True)
    cfg["control_dir"].mkdir(parents=True, exist_ok=True)
    cfg["no_aplica_dir"].mkdir(parents=True, exist_ok=True)

    log = RunLog(cfg["control_dir"])
    log.info("start", limit=args.limit, since=cfg["date_from"], until=cfg["date_to"],
             dry_run=args.dry_run, source=str(cfg["source_excel"]))

    if not cfg["source_excel"].exists():
        log.error("source_missing", path=str(cfg["source_excel"]))
        sys.exit(1)

    if args.validate_source:
        rows = load_expected_rows(cfg["source_excel"])
        log.info("source_validated", rows=len(rows))
        print(f"\n  Fuente: {cfg['source_excel']}")
        print(f"  Filas extraidas: {len(rows)}")
        print(f"\n  Primeras 5 filas:")
        for r in rows[:5]:
            print(f"    NUMDOCTRA={r[0]}  fecha={r[1]}  valor=${r[5]}")
        print(f"\n  Ultimas 3 filas:")
        for r in rows[-3:]:
            print(f"    NUMDOCTRA={r[0]}  fecha={r[1]}  valor=${r[5]}")
        return

    control_path = cfg["control_dir"] / cfg["control_filename"]

    if args.listar_faltantes:
        if not control_path.exists():
            log.error("control_missing_for_listing", path=str(control_path))
            sys.exit(1)
        listar_faltantes(control_path, log)
        return

    if args.marcar_faltantes:
        if not control_path.exists():
            log.error("control_missing_for_marking", path=str(control_path))
            sys.exit(1)
        n = mark_missing_facturas(control_path, log)
        print(f"\n  ✓ {n} filas marcadas con 'No se encontró factura' en col Observaciones")
        return

    if args.reprocesar_diferencias:
        if not control_path.exists():
            log.error("control_missing_for_reprocess", path=str(control_path))
            sys.exit(1)
        deleted, marcados = reprocesar_diferencias(control_path, cfg["facturas_dir"], log)
        print(f"\n  ✓ {marcados} facturas con 'Remisión con valor diferente' encontradas")
        print(f"  ✓ {deleted} carpetas FC<num> borradas (listas para reprocesar)")
        print(f"\n  Ahora corre: python conciliador.py  (o con --since/--until)")
        return

    if args.detectar_duplicados:
        if not control_path.exists():
            log.error("control_missing_for_dedup", path=str(control_path))
            sys.exit(1)
        n = detectar_duplicados_remisiones(control_path, log)
        print(f"\n  ✓ {n} filas marcadas como duplicado en hoja 'Detalle Remisiones'")
        print(f"  Abre el Excel y mira la columna Observaciones para ver los detalles.")
        return

    if args.informe:
        if not control_path.exists():
            log.error("control_missing_for_informe", path=str(control_path))
            sys.exit(1)
        generar_informe(control_path, log)
        return

    if args.informe_duplicados:
        if not control_path.exists():
            log.error("control_missing_for_informe_dup", path=str(control_path))
            sys.exit(1)
        generar_informe_duplicados(control_path, cfg["facturas_dir"], log)
        return

    if args.informe_criticos:
        if not control_path.exists():
            log.error("control_missing_for_informe_crit", path=str(control_path))
            sys.exit(1)
        generar_informe_criticos(control_path, cfg["facturas_dir"],
                                  cfg["tolerance_pesos"], log)
        return

    if args.informe_reclamacion:
        if not control_path.exists():
            log.error("control_missing_for_informe_reclam", path=str(control_path))
            sys.exit(1)
        generar_informe_reclamacion(control_path, cfg["facturas_dir"],
                                     cfg["tolerance_pesos"], log)
        return

    if args.enviar_email_revision:
        if not control_path.exists():
            log.error("control_missing_for_email", path=str(control_path))
            sys.exit(1)
        to_emails = [e.strip() for e in args.enviar_email_revision.split(",") if e.strip()]
        if not to_emails:
            print("ERROR: pasa al menos una direccion separada por coma")
            sys.exit(1)
        enviar_informe_email(control_path, to_emails, cfg, log)
        return

    if args.rebuild_resumen:
        if not control_path.exists():
            log.error("control_missing_for_rebuild_resumen", path=str(control_path))
            sys.exit(1)
        wb = load_workbook(str(control_path))
        cons = wb["Conciliación"]
        last_data_row = cons.max_row
        if "Resumen" in wb.sheetnames:
            del wb["Resumen"]
        _build_resumen_sheet(wb, last_data_row)
        idx_resumen = wb.sheetnames.index("Resumen")
        wb.move_sheet("Resumen", offset=-idx_resumen + 1)
        wb.save(str(control_path))
        log.info("resumen_rebuilt", last_data_row=last_data_row)
        print(f"\n  ✓ Hoja Resumen regenerada con labels actuales")
        # Desglose mensual de faltantes
        update_faltantes_breakdown_in_resumen(control_path, log)
        # Hallazgos forenses (casos criticos, etc.)
        agregar_hallazgos_a_resumen(control_path, cfg["facturas_dir"],
                                     cfg["tolerance_pesos"], log)
        return

    bootstrap_control(control_path, cfg["source_excel"], log)
    expected = load_expected_numdoctras(cfg["source_excel"])
    log.info("expected_loaded", count=len(expected))

    service = get_gmail_service(cfg, log)
    ids = gmail_search(service, cfg, log)
    meta: list[tuple[str, datetime, email.message.Message]] = []
    non_invoice_count = 0
    for mid in ids:
        try:
            m = fetch_message(service, mid)
            subj = decode_subject(m.get("Subject", ""))
            if not extract_numdoctra(subj):
                non_invoice_count += 1
                continue
            meta.append((mid, message_date(m), m))
        except Exception as e:
            log.error("fetch_failed", msg_id=mid, err=str(e))
    if non_invoice_count > 0:
        log.info("non_invoices_filtered", count=non_invoice_count)
    meta.sort(key=lambda x: x[1])
    if args.limit and args.limit > 0:
        meta = meta[:args.limit]
    log.info("to_process", count=len(meta))

    summary = {
        "emails_read": len(meta), "zips_downloaded": 0, "facturas_new": 0,
        "facturas_skipped": 0, "errors": 0, "inconsistencies": 0, "detail": "",
    }

    if args.dry_run:
        for mid, dt, m in meta:
            subj = decode_subject(m.get("Subject", ""))
            print(f"  [DRY] {dt.isoformat()} | {extract_numdoctra(subj)} | {subj}")
        log.info("dry_run_done")
        return

    # Cargar indice de remision_no de procesamientos anteriores para detectar
    # duplicados al vuelo (mismo numero de remision usado en 2 facturas)
    remision_no_index = load_remision_no_index(control_path)
    log.info("remision_no_index_loaded", count=len(remision_no_index))

    # Configuracion paralela: ajustable via env
    workers = int(os.environ.get("CONCILIADOR_WORKERS", "5"))
    batch_size = int(os.environ.get("CONCILIADOR_BATCH_SIZE", "20"))
    log.info("parallel_config", workers=workers, batch_size=batch_size)

    batch: list[dict] = []
    total = len(meta)
    completed_count = 0

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {
            executor.submit(process_one_email_no_io, cfg, mid, m, expected, log): mid
            for mid, _dt, m in meta
        }

        for f in as_completed(futures):
            completed_count += 1
            try:
                result = f.result()
            except Exception as e:
                mid = futures[f]
                log.error("process_failed", msg_id=mid, err=str(e))
                summary["errors"] += 1
                continue

            status = result.get("status")
            numdoctra = result.get("numdoctra")

            if status == "to_write":
                batch.append(result)
                summary["zips_downloaded"] += 1
                if len(batch) >= batch_size:
                    write_batch_to_excel(control_path, batch, remision_no_index,
                                         cfg, service, summary, log)
                    batch = []
            elif status == "already_processed":
                log.info("already_processed_skip", numdoctra=numdoctra)
                summary["facturas_skipped"] += 1
                add_label(service, result["msg_id"], cfg["label_processed"])
            elif status == "skipped_not_expected":
                log.warn("numdoctra_not_expected", numdoctra=numdoctra)
                summary["facturas_skipped"] += 1
            elif status == "skipped_emisor_distinto":
                log.warn("emisor_distinto", numdoctra=numdoctra,
                         nit_found=result.get("nit_found"))
                summary["facturas_skipped"] += 1
            elif status == "skipped_no_numdoctra":
                log.warn("no_numdoctra_in_subject", subject=result.get("subject"))
                summary["errors"] += 1
            elif status and status.startswith("error_"):
                log.warn(status, numdoctra=numdoctra)
                summary["errors"] += 1

            # Progreso heartbeat cada 25 facturas
            if completed_count % 25 == 0:
                log.info("progress", completed=completed_count, total=total,
                         pct=round(completed_count * 100 / total, 1))

    # Flush ultimo batch incompleto
    if batch:
        write_batch_to_excel(control_path, batch, remision_no_index,
                             cfg, service, summary, log)

    append_log_row(control_path, summary)
    # Marcar las filas del control sin correo recibido con "No se encontró factura"
    # en la columna Observaciones
    n_missing = mark_missing_facturas(control_path, log)
    summary["missing_marked"] = n_missing
    log.info("done", **summary)


if __name__ == "__main__":
    main()
