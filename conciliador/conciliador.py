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
    client = anthropic.Anthropic(api_key=api_key)
    model = os.environ.get("ANTHROPIC_VISION_MODEL", "claude-sonnet-4-6")
    max_retries = int(os.environ.get("ANTHROPIC_MAX_RETRIES", "4"))

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
    kpi_card(14, "A favor de Nautiturismo (factura > remisión)",
             f'=SUMIF({rng_l},">0")', MONEY_FMT, fill_red, money_font)
    kpi_card(15, "A favor de Todomar (factura < remisión)",
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

    ws.column_dimensions["A"].width = 48
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
    el header para que las nuevas escrituras a esa col tengan etiqueta."""
    col_idx = COL["Observaciones"]
    cell = ws.cell(row=1, column=col_idx)
    if cell.value != "Observaciones":
        cell.value = "Observaciones"
        cell.font = Font(bold=True, color="FFFFFF", size=11)
        cell.fill = PatternFill("solid", fgColor="305496")
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.border = THIN_BORDER
        ws.column_dimensions[get_column_letter(col_idx)].width = 50


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
    return marked


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

    for mid, _dt, m in meta:
        try:
            process_one_email(cfg, mid, m, expected, log, summary, service,
                              remision_no_index=remision_no_index)
        except Exception as e:
            log.error("process_failed", msg_id=mid, err=str(e))
            summary["errors"] += 1

    append_log_row(control_path, summary)
    # Marcar las filas del control sin correo recibido con "No se encontró factura"
    # en la columna Observaciones
    n_missing = mark_missing_facturas(control_path, log)
    summary["missing_marked"] = n_missing
    log.info("done", **summary)


if __name__ == "__main__":
    main()
