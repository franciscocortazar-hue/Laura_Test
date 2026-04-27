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
from dotenv import load_dotenv
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from openpyxl import Workbook, load_workbook
from openpyxl.formatting.rule import CellIsRule, FormulaRule
from openpyxl.styles import Alignment, Font, PatternFill
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
    folder.mkdir(parents=True, exist_ok=True)
    extracted: list[Path] = []
    with zipfile.ZipFile(BytesIO(zip_bytes)) as z:
        for name in z.namelist():
            target = folder / Path(name).name  # flatten
            if not name or name.endswith("/"):
                continue
            with z.open(name) as src, target.open("wb") as dst:
                shutil.copyfileobj(src, dst)
            extracted.append(target)
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
        "raw_text_sample": text[:200],
    }


def _find_nit(text: str) -> str | None:
    m = re.search(r"NIT[:\s]*([\d.\-]+)", text or "", re.IGNORECASE)
    if m:
        return re.sub(r"[.\-\s]", "", m.group(1))
    return None


def extract_remision_data(pdf_path: Path) -> dict:
    text = pdf_text(pdf_path)
    return {
        "valor": find_money_after(text, [
            "TOTAL", "VALOR TOTAL", "Total"
        ]),
        "bote": _find_bote(text),
        "fecha_hora": _find_fecha_hora(text),
        "raw_text_sample": text[:300],
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

def conciliate(valor_factura: float, valores_remision: list[float], tol: float) -> tuple[str, float]:
    if not valores_remision:
        return ("No hay remisión", 0.0)
    suma = sum(valores_remision)
    diff = round(valor_factura - suma, 2)
    if abs(diff) <= tol:
        return ("OK", 0.0)
    if len(valores_remision) >= 2:
        return (
            f"Remisión con valor diferente ({len(valores_remision)} remisiones, no coincide con el valor facturado)",
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
    "Link factura", "Link remisión(es)", "Última actualización",
]
COL = {h: i + 1 for i, h in enumerate(CONTROL_HEADERS)}
MONEY_FMT = '"$"#,##0;[Red]-"$"#,##0'
HYPERLINK_FONT = Font(color="0563C1", underline="single")


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


def bootstrap_control(control_path: Path, source_excel: Path, log: RunLog) -> None:
    if control_path.exists():
        log.info("control_exists", path=str(control_path))
        return
    log.info("control_bootstrap", path=str(control_path), source=str(source_excel))
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
    wb = Workbook()
    ws = wb.active
    ws.title = "Conciliación"

    header_font = Font(bold=True, color="FFFFFF")
    header_fill = PatternFill("solid", fgColor="305496")
    for col_idx, name in enumerate(CONTROL_HEADERS, start=1):
        c = ws.cell(row=1, column=col_idx, value=name)
        c.font = header_font
        c.fill = header_fill
        c.alignment = Alignment(horizontal="center", vertical="center")

    for r, row in enumerate(rows, start=2):
        ws.cell(row=r, column=1, value=row[0])
        ws.cell(row=r, column=2, value=row[1])
        ws.cell(row=r, column=3, value=row[2])
        ws.cell(row=r, column=4, value=row[3])
        ws.cell(row=r, column=5, value=row[4])
        ws.cell(row=r, column=6, value=row[5])

    last_row = len(rows) + 1
    for col_letter in ("F", "I", "L"):
        for r in range(2, last_row + 1):
            ws[f"{col_letter}{r}"].number_format = MONEY_FMT

    ws.freeze_panes = "A2"
    ws.auto_filter.ref = f"A1:{get_column_letter(len(CONTROL_HEADERS))}{last_row}"

    green = PatternFill("solid", fgColor="C6EFCE")
    yellow = PatternFill("solid", fgColor="FFEB9C")
    red = PatternFill("solid", fgColor="FFC7CE")
    orange = PatternFill("solid", fgColor="FFD9A6")
    rng_k = f"K2:K{last_row}"
    ws.conditional_formatting.add(
        rng_k, FormulaRule(formula=[f'EXACT(K2,"OK")'], fill=green)
    )
    ws.conditional_formatting.add(
        rng_k, FormulaRule(formula=[f'EXACT(K2,"No hay remisión")'], fill=yellow)
    )
    ws.conditional_formatting.add(
        rng_k, FormulaRule(formula=[f'ISNUMBER(SEARCH("Remisión con valor diferente",K2))'], fill=red)
    )
    rng_l = f"L2:L{last_row}"
    ws.conditional_formatting.add(
        rng_l, CellIsRule(operator="greaterThan", formula=["1000"], fill=red)
    )
    ws.conditional_formatting.add(
        rng_l, CellIsRule(operator="lessThan", formula=["-1000"], fill=orange)
    )

    widths = {"A": 12, "B": 13, "C": 22, "D": 14, "E": 8, "F": 16, "G": 18,
              "H": 22, "I": 16, "J": 8, "K": 38, "L": 16, "M": 50, "N": 50, "O": 22}
    for letter, w in widths.items():
        ws.column_dimensions[letter].width = w

    _build_resumen_sheet(wb, last_row)
    _build_log_sheet(wb)

    control_path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(str(control_path))
    log.info("control_created", rows=len(rows))


def _build_resumen_sheet(wb: Workbook, last_data_row: int) -> None:
    ws = wb.create_sheet("Resumen")
    rng_k = f"'Conciliación'!K2:K{last_data_row}"
    rng_l = f"'Conciliación'!L2:L{last_data_row}"
    rng_f = f"'Conciliación'!F2:F{last_data_row}"
    rng_i = f"'Conciliación'!I2:I{last_data_row}"

    rows = [
        ("Métrica", "Valor", None),
        ("Total facturas en alcance", f"=COUNTA('Conciliación'!A2:A{last_data_row})", None),
        ("Total facturado ($)", f"=SUM({rng_f})", MONEY_FMT),
        ("", "", None),
        ("Conciliación: OK", f'=COUNTIF({rng_k},"OK")', None),
        ("Conciliación: Sin remisión", f'=COUNTIF({rng_k},"No hay remisión")', None),
        ("Conciliación: Con diferencia", f'=COUNTIF({rng_k},"Remisión con valor diferente*")', None),
        ("", "", None),
        ("Diferencia a favor de Nautiturismo", f'=SUMIF({rng_l},">0")', MONEY_FMT),
        ("Diferencia a favor de Todomar", f'=SUMIF({rng_l},"<0")', MONEY_FMT),
        ("Neto de diferencias", f"=SUM({rng_l})", MONEY_FMT),
        ("", "", None),
        ("Facturas procesadas", f'=COUNTIFS({rng_k},"<>")', None),
        ("Facturas pendientes (sin correo)", f'=COUNTBLANK({rng_k})', None),
        ("Total remisiones leídas", f"=SUM({rng_i})", MONEY_FMT),
    ]
    for r, (label, value, fmt) in enumerate(rows, start=1):
        ws.cell(row=r, column=1, value=label)
        c = ws.cell(row=r, column=2, value=value)
        if fmt:
            c.number_format = fmt
        if r == 1:
            ws.cell(row=r, column=1).font = Font(bold=True)
            ws.cell(row=r, column=2).font = Font(bold=True)
    ws.column_dimensions["A"].width = 38
    ws.column_dimensions["B"].width = 22


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


def find_row_by_numdoctra(ws, numdoctra: int | str) -> int | None:
    target = str(numdoctra).strip()
    for r in range(2, ws.max_row + 1):
        v = ws.cell(row=r, column=1).value
        if v is None:
            continue
        if str(int(v) if isinstance(v, float) else v).strip() == target:
            return r
    return None


def update_control_row(
    control_path: Path,
    numdoctra: str,
    factura_data: dict,
    remisiones_data: list[dict],
    conciliacion: str,
    valor_diff: float,
    factura_link: Path | None,
    remision_links: list[Path],
    log: RunLog,
) -> bool:
    wb = load_workbook(str(control_path))
    ws = wb["Conciliación"]
    row = find_row_by_numdoctra(ws, numdoctra)
    if row is None:
        log.warn("numdoctra_not_in_control", numdoctra=numdoctra)
        wb.close()
        return False
    bote = ", ".join(filter(None, [r.get("bote") for r in remisiones_data])) or None
    fecha_h = next((r.get("fecha_hora") for r in remisiones_data if r.get("fecha_hora")), None)
    suma_rem = sum(r.get("valor", 0) or 0 for r in remisiones_data)

    ws.cell(row=row, column=COL["Nombre de Bote"], value=bote)
    ws.cell(row=row, column=COL["Fecha y hora de tanqueo"], value=fecha_h)
    c_vr = ws.cell(row=row, column=COL["Valor remisión"], value=suma_rem if remisiones_data else None)
    if remisiones_data:
        c_vr.number_format = MONEY_FMT
    ws.cell(row=row, column=COL["# Remisiones"], value=len(remisiones_data))
    ws.cell(row=row, column=COL["Conciliación"], value=conciliacion)
    c_diff = ws.cell(row=row, column=COL["Valor (diferencia)"], value=valor_diff)
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

    wb.save(str(control_path))
    return True


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

    remisiones_data = [extract_remision_data(p) for p in remisiones_paths]

    if factura_data.get("valor") is None:
        log.warn("factura_value_not_extracted", numdoctra=numdoctra,
                 sample=factura_data.get("raw_text_sample"))
        summary["errors"] += 1
        return

    valores_rem = [r["valor"] for r in remisiones_data if r.get("valor") is not None]
    conc, diff = conciliate(factura_data["valor"], valores_rem, cfg["tolerance_pesos"])

    ok = update_control_row(
        cfg["control_dir"] / cfg["control_filename"],
        numdoctra, factura_data, remisiones_data, conc, diff,
        factura_path, remisiones_paths, log,
    )
    if ok:
        summary["facturas_new"] += 1
        add_label(service, msg_id, cfg["label_processed"])
        log.info(
            "conciliated",
            numdoctra=numdoctra, valor_factura=factura_data["valor"],
            valor_remision=sum(valores_rem) if valores_rem else 0,
            n_remisiones=len(remisiones_data), conciliacion=conc, diferencia=diff,
        )


def load_expected_numdoctras(source_excel: Path) -> set[str]:
    wb = load_workbook(str(source_excel), data_only=True)
    ws = wb["Hoja1"]
    out: set[str] = set()
    for r in range(2, ws.max_row + 1):
        v = ws.cell(row=r, column=6).value
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
    args = parser.parse_args()

    cfg = load_config()
    if args.since:
        cfg["date_from"] = args.since
    if args.until:
        cfg["date_to"] = args.until

    cfg["facturas_dir"].mkdir(parents=True, exist_ok=True)
    cfg["control_dir"].mkdir(parents=True, exist_ok=True)
    cfg["no_aplica_dir"].mkdir(parents=True, exist_ok=True)

    log = RunLog(cfg["control_dir"])
    log.info("start", limit=args.limit, since=cfg["date_from"], until=cfg["date_to"],
             dry_run=args.dry_run)

    if not cfg["source_excel"].exists():
        log.error("source_excel_missing", path=str(cfg["source_excel"]))
        sys.exit(1)

    control_path = cfg["control_dir"] / cfg["control_filename"]
    bootstrap_control(control_path, cfg["source_excel"], log)
    expected = load_expected_numdoctras(cfg["source_excel"])
    log.info("expected_loaded", count=len(expected))

    service = get_gmail_service(cfg, log)
    ids = gmail_search(service, cfg, log)
    meta: list[tuple[str, datetime, email.message.Message]] = []
    for mid in ids:
        try:
            m = fetch_message(service, mid)
            meta.append((mid, message_date(m), m))
        except Exception as e:
            log.error("fetch_failed", msg_id=mid, err=str(e))
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

    for mid, _dt, m in meta:
        try:
            process_one_email(cfg, mid, m, expected, log, summary, service)
        except Exception as e:
            log.error("process_failed", msg_id=mid, err=str(e))
            summary["errors"] += 1

    append_log_row(control_path, summary)
    log.info("done", **summary)


if __name__ == "__main__":
    main()
