#!/usr/bin/env python3
"""Druckbare Vokabel-Lernkarten im bestehenden Duplex-Layout erzeugen.

Liest vokabeln.json und schreibt A4-PDFs: 3×8 Karten pro Blatt,
Vorderseite Englisch (DejaVu Sans Bold), Rückseite Deutsch (DejaVu Sans),
gespiegelt für Duplex an der langen Kante, Schnittlinien und Seitenfuß.

Beispiele:
  python tools/lernkarten/generate.py --gesamt
  python tools/lernkarten/generate.py --delta-nach v212
  python tools/lernkarten/generate.py --gesamt --delta-nach v212 --stand
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date
from pathlib import Path

from reportlab.lib.colors import Color
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

# --- Layout, 1:1 aus dem bestehenden lernkarten-duplex.pdf (Stand 2026-10-24) ---
PAGE_W, PAGE_H = A4
MARGIN_X = 15 * mm
MARGIN_Y = 12.5 * mm
COLS, ROWS = 3, 8
COL_W = 60 * mm
ROW_H = 34 * mm
GRID_LEFT = MARGIN_X
GRID_BOTTOM = MARGIN_Y
GRID_RIGHT = MARGIN_X + COLS * COL_W
GRID_TOP = MARGIN_Y + ROWS * ROW_H

GRID_COLOR = Color(0.62, 0.62, 0.62)
GRID_WIDTH = 0.3
CROP_COLOR = Color(0.35, 0.35, 0.35)
CROP_WIDTH = 0.5
CROP_GAP = 1.2 * mm
CROP_LEN = 4 * mm

TEXT_COLOR = Color(0.1, 0.12, 0.18)
LABEL_COLOR = GRID_COLOR
FOOTER_SIZE = 6
LABEL_SIZE = 6
LABEL_PAD_RIGHT = 1.8 * mm
LABEL_PAD_BOTTOM = 1.6 * mm
FOOTER_Y = 3.2 * mm

FONT_REG = "DejaVuLern"
FONT_BOLD = "DejaVuLern-Bold"
MAX_SIZE = 17.0
MIN_SIZE = 9.0
SIZE_STEP = 0.5
# 4,5 mm Innenabstand; typografische Zeilenabstände wie im Original
TEXT_PAD_X = 4.5 * mm
MAX_TEXT_W = COL_W - 2 * TEXT_PAD_X
LINE_LEADING = 1.22
BASELINE_SHIFT = 0.34  # optische Mitte der Grundlinie relativ zur Zellenmitte
ASCENT = 0.7597656
DESCENT = 0.2402344

FONT_CANDIDATES = [
    Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
    Path("/usr/share/fonts/dejavu/DejaVuSans.ttf"),
    Path("/usr/share/fonts/TTF/DejaVuSans.ttf"),
    Path(__file__).resolve().parent / "fonts" / "DejaVuSans.ttf",
]


def _register_fonts() -> None:
    regular = next((p for p in FONT_CANDIDATES if p.exists()), None)
    if regular is None:
        sys.exit(
            "DejaVuSans.ttf nicht gefunden. Bitte fonts-dejavu-core installieren "
            "oder die Datei nach tools/lernkarten/fonts/ legen."
        )
    bold = regular.with_name("DejaVuSans-Bold.ttf")
    if not bold.exists():
        sys.exit(f"DejaVuSans-Bold.ttf fehlt neben {regular}")
    if FONT_REG not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont(FONT_REG, str(regular)))
        pdfmetrics.registerFont(TTFont(FONT_BOLD, str(bold)))


def _string_w(text: str, font: str, size: float) -> float:
    return pdfmetrics.stringWidth(text, font, size)


def _wrap_spaces(text: str, font: str, size: float, max_w: float) -> list[str]:
    """Greedy-Umbruch nur an Leerzeichen."""
    text = " ".join(text.split())
    if not text:
        return [""]
    if _string_w(text, font, size) <= max_w:
        return [text]
    lines: list[str] = []
    rest = text
    while rest:
        best: int | None = None
        for i, ch in enumerate(rest):
            at_end = i == len(rest) - 1
            if ch.isspace() or at_end:
                trial = rest[: i + 1].rstrip()
                if _string_w(trial, font, size) <= max_w:
                    best = i
                elif best is not None:
                    break
                else:
                    best = i
                    break
        assert best is not None
        line = rest[: best + 1].rstrip()
        lines.append(line)
        rest = rest[best + 1 :].lstrip()
    return lines


def _pack_units(units: list[str], font: str, size: float, max_w: float) -> list[str]:
    """Einheiten (typisch an '/' getrennt, Trennzeichen bleibt links) zeilenweise packen."""
    lines: list[str] = []
    cur = ""
    for unit in units:
        if unit == "":
            continue
        cand = f"{cur}{unit}" if cur else unit
        if _string_w(cand, font, size) <= max_w:
            cur = cand
            continue
        if cur:
            lines.append(cur)
        if _string_w(unit, font, size) <= max_w:
            cur = unit
        else:
            lines.extend(_wrap_spaces(unit, font, size, max_w))
            cur = ""
    if cur:
        lines.append(cur)
    return lines


def wrap_text(text: str, font: str, size: float, max_w: float) -> list[str]:
    """Umbruch wie im Original: passt alles, eine Zeile.

    Sonst Semikolon als harte Trennung (verschiedene Bedeutungen),
    Schrägstrich als packbare Alternative, dann Leerzeichen.
    """
    text = " ".join(text.split())
    if not text:
        return [""]
    if _string_w(text, font, size) <= max_w:
        return [text]
    if ";" in text:
        parts = re.split(r"(?<=;)\s*", text)
        lines: list[str] = []
        for part in parts:
            if not part:
                continue
            lines.extend(_wrap_slash_or_space(part, font, size, max_w))
        return lines
    return _wrap_slash_or_space(text, font, size, max_w)


def _wrap_slash_or_space(text: str, font: str, size: float, max_w: float) -> list[str]:
    if _string_w(text, font, size) <= max_w:
        return [text]
    if "/" in text:
        units = re.split(r"(?<=/)", text)
        return _pack_units(units, font, size, max_w)
    return _wrap_spaces(text, font, size, max_w)


def _block_fits(n_lines: int, size: float) -> bool:
    """Passt der Textblock vertikal in die Karte (ohne das S.-Kürzel zu überdecken)?"""
    mid = GRID_BOTTOM + ROW_H / 2  # relative: use cell-local
    # local coordinates: cell bottom = 0, mid = ROW_H/2
    mid_local = ROW_H / 2
    gap = LINE_LEADING * size
    mid_baselines = mid_local - BASELINE_SHIFT * size
    last = mid_baselines - (n_lines - 1) * gap / 2
    first = mid_baselines + (n_lines - 1) * gap / 2
    text_bot = last - DESCENT * size
    text_top = first + ASCENT * size
    label_top = LABEL_PAD_BOTTOM + ASCENT * LABEL_SIZE + 0.4 * mm
    top_pad = 2.0 * mm
    return text_bot >= label_top and text_top <= ROW_H - top_pad


def fit_text(text: str, font: str) -> tuple[float, list[str]]:
    size = MAX_SIZE
    chosen: tuple[float, list[str]] | None = None
    while size >= MIN_SIZE - 1e-9:
        lines = wrap_text(text, font, size, MAX_TEXT_W)
        if all(_string_w(line, font, size) <= MAX_TEXT_W + 0.05 for line in lines) and _block_fits(
            len(lines), size
        ):
            chosen = (size, lines)
            break
        size = round(size - SIZE_STEP, 2)
    if chosen is None:
        lines = wrap_text(text, font, MIN_SIZE, MAX_TEXT_W)
        chosen = (MIN_SIZE, lines)
    return chosen


def _cell_box(col: int, row_from_top: int) -> tuple[float, float, float, float]:
    """(left, bottom, right, top) – row 0 ist oben."""
    left = GRID_LEFT + col * COL_W
    top = GRID_TOP - row_from_top * ROW_H
    bottom = top - ROW_H
    return left, bottom, left + COL_W, top


def draw_grid_and_crops(c: canvas.Canvas) -> None:
    c.setStrokeColor(GRID_COLOR)
    c.setLineWidth(GRID_WIDTH)
    for i in range(COLS + 1):
        x = GRID_LEFT + i * COL_W
        c.line(x, GRID_BOTTOM, x, GRID_TOP)
    for j in range(ROWS + 1):
        y = GRID_BOTTOM + j * ROW_H
        c.line(GRID_LEFT, y, GRID_RIGHT, y)

    c.setStrokeColor(CROP_COLOR)
    c.setLineWidth(CROP_WIDTH)
    xs = [GRID_LEFT + i * COL_W for i in range(COLS + 1)]
    ys = [GRID_BOTTOM + j * ROW_H for j in range(ROWS + 1)]
    for x in xs:
        c.line(x, GRID_TOP + CROP_GAP, x, GRID_TOP + CROP_GAP + CROP_LEN)
        c.line(x, GRID_BOTTOM - CROP_GAP, x, GRID_BOTTOM - CROP_GAP - CROP_LEN)
    for y in ys:
        c.line(GRID_LEFT - CROP_GAP, y, GRID_LEFT - CROP_GAP - CROP_LEN, y)
        c.line(GRID_RIGHT + CROP_GAP, y, GRID_RIGHT + CROP_GAP + CROP_LEN, y)


def draw_footer(c: canvas.Canvas, text: str) -> None:
    c.setFillColor(LABEL_COLOR)
    c.setFont(FONT_REG, FOOTER_SIZE)
    c.drawCentredString(PAGE_W / 2, FOOTER_Y, text)


def draw_card_text(
    c: canvas.Canvas,
    col: int,
    row: int,
    lines: list[str],
    size: float,
    font: str,
    label: str | None,
) -> None:
    left, bottom, right, top = _cell_box(col, row)
    mid_y = (top + bottom) / 2
    gap = LINE_LEADING * size
    mid_baselines = mid_y - BASELINE_SHIFT * size
    n = max(len(lines), 1)
    first = mid_baselines + (n - 1) * gap / 2
    c.setFillColor(TEXT_COLOR)
    for i, line in enumerate(lines):
        y = first - i * gap
        c.setFont(font, size)
        c.drawCentredString((left + right) / 2, y, line)
    if label:
        c.setFillColor(LABEL_COLOR)
        c.setFont(FONT_REG, LABEL_SIZE)
        x = right - LABEL_PAD_RIGHT - _string_w(label, FONT_REG, LABEL_SIZE)
        y = bottom + LABEL_PAD_BOTTOM
        c.drawString(x, y, label)


def draw_sheet(
    c: canvas.Canvas,
    cards: list[dict | None],
    sheet_no: int,
    sheet_count: int,
    side: str,
    mirror: bool,
) -> None:
    """side: 'en' oder 'de'. cards in Zeilenreihenfolge (24 Einträge, Lücken None)."""
    draw_grid_and_crops(c)
    if side == "en":
        footer = f"Blatt {sheet_no}/{sheet_count} · Vorderseite Englisch · Duplex lange Kante, 100 %"
    else:
        footer = f"Blatt {sheet_no}/{sheet_count} · Rückseite Deutsch · Duplex lange Kante, 100 %"
    draw_footer(c, footer)
    font = FONT_BOLD if side == "en" else FONT_REG
    field = "en" if side == "en" else "de"
    for idx in range(COLS * ROWS):
        row, col = divmod(idx, COLS)
        src_col = (COLS - 1 - col) if mirror else col
        src_idx = row * COLS + src_col
        card = cards[src_idx] if src_idx < len(cards) else None
        if not card:
            continue
        size, lines = fit_text(card[field], font)
        seite = card.get("seite")
        label = f"S.{seite}" if seite not in (None, "") else None
        draw_card_text(c, col, row, lines, size, font, label)
    c.showPage()


def chunk(items: list, size: int) -> list[list]:
    out = []
    for i in range(0, len(items), size):
        block = items[i : i + size]
        if len(block) < size:
            block = block + [None] * (size - len(block))
        out.append(block)
    return out or [[None] * size]


def write_pdf(path: Path, items: list[dict], title: str) -> int:
    _register_fonts()
    path.parent.mkdir(parents=True, exist_ok=True)
    sheets = chunk(items, COLS * ROWS)
    c = canvas.Canvas(str(path), pagesize=A4)
    c.setTitle(title)
    c.setSubject("Englisch-Lernkarten zum Ausschneiden")
    c.setKeywords("Englisch, Vokabeln, Lernkarten")
    c.setAuthor("Lerntrainer")
    c.setCreator("Lerntrainer")
    n = len(sheets)
    for i, cards in enumerate(sheets, start=1):
        draw_sheet(c, cards, i, n, "en", mirror=False)
        draw_sheet(c, cards, i, n, "de", mirror=True)
    c.save()
    return n * 2


def load_vocab(path: Path) -> list[dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    items = data if isinstance(data, list) else data.get("vokabeln") or data.get("items")
    if not isinstance(items, list):
        sys.exit(f"Unerwartetes Format in {path}")
    return items


def id_num(vid: str) -> int:
    m = re.search(r"(\d+)", vid or "")
    return int(m.group(1)) if m else -1


def default_json() -> Path:
    here = Path(__file__).resolve()
    candidates = [
        here.parents[2] / "vokabeln.json",
        Path.cwd() / "vokabeln.json",
    ]
    for p in candidates:
        if p.exists():
            return p
    return candidates[0]


def default_out_dir() -> Path:
    here = Path(__file__).resolve()
    return here.parents[2] / "lernkarten"


def write_stand(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Lernkarten-PDFs aus vokabeln.json erzeugen")
    p.add_argument("--json", type=Path, default=None, help="Pfad zu vokabeln.json")
    p.add_argument("--out-dir", type=Path, default=None, help="Zielordner für die PDFs")
    p.add_argument("--datum", default=None, help="Datum im Dateinamen, Standard: heute (JJJJ-MM-TT)")
    p.add_argument("--gesamt", action="store_true", help="Gesamtset aller Vokabeln schreiben")
    p.add_argument(
        "--delta-nach",
        metavar="ID",
        default=None,
        help="Delta-Set: nur Vokabeln mit ID nach dieser (z.B. v212)",
    )
    p.add_argument("--stand", action="store_true", help="lernkarten/STAND.json schreiben")
    p.add_argument(
        "--title",
        default="Englisch-Lernkarten",
        help="PDF-Titel (kein Schülername)",
    )
    args = p.parse_args(argv)
    if not args.gesamt and not args.delta_nach and not args.stand:
        args.gesamt = True
        args.stand = True
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    json_path = args.json or default_json()
    out_dir = args.out_dir or default_out_dir()
    datum = args.datum or date.today().isoformat()
    items = load_vocab(json_path)
    if not items:
        sys.exit("Keine Vokabeln gefunden.")
    items_sorted = sorted(items, key=lambda it: id_num(it["id"]))
    first_id, last_id = items_sorted[0]["id"], items_sorted[-1]["id"]

    stand_path = out_dir / "STAND.json"
    previous = None
    if stand_path.exists():
        try:
            previous = json.loads(stand_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            previous = None

    result = {
        "datum": datum,
        "quelle": "vokabeln.json",
        "anzahl": len(items_sorted),
        "erste_id": first_id,
        "letzte_id": last_id,
        "regel": "Bei jedem Update von vokabeln.json Gesamtset und Delta-Set neu erzeugen.",
    }
    if previous and previous.get("letzte_id") and previous.get("letzte_id") != last_id:
        result["vorheriger_kartenstand"] = {
            "datum": previous.get("datum"),
            "anzahl": previous.get("anzahl"),
            "erste_id": previous.get("erste_id"),
            "letzte_id": previous.get("letzte_id"),
            "gesamt": (previous.get("gesamt") or {}).get("datei"),
            "delta": (previous.get("delta") or {}).get("datei"),
        }

    if args.gesamt:
        dest = out_dir / f"lernkarten-gesamt-{datum}.pdf"
        pages = write_pdf(dest, items_sorted, args.title)
        result["gesamt"] = {
            "datei": str(Path("lernkarten") / dest.name),
            "vokabeln": len(items_sorted),
            "id_von": first_id,
            "id_bis": last_id,
            "seiten": pages,
        }
        print(f"Gesamtset: {dest} ({len(items_sorted)} Vokabeln, {pages} Seiten)")

    if args.delta_nach:
        threshold = id_num(args.delta_nach)
        delta = [it for it in items_sorted if id_num(it["id"]) > threshold]
        dest = out_dir / f"lernkarten-delta-{datum}.pdf"
        if not delta:
            sys.exit(f"Keine Vokabeln nach {args.delta_nach}.")
        pages = write_pdf(dest, delta, f"{args.title} – neu seit {args.delta_nach}")
        result["delta"] = {
            "datei": str(Path("lernkarten") / dest.name),
            "nach_id": args.delta_nach,
            "vokabeln": len(delta),
            "id_von": delta[0]["id"],
            "id_bis": delta[-1]["id"],
            "seiten": pages,
        }
        print(f"Delta-Set: {dest} ({len(delta)} Vokabeln ab {delta[0]['id']}, {pages} Seiten)")

    if args.stand:
        write_stand(stand_path, result)
        print(f"Stand: {stand_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
