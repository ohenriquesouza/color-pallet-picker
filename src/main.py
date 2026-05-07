"""
Extrai as cores dominantes de imagens e gera um relatório em PDF.
"""

import os
import sys
from pathlib import Path
from datetime import datetime

import numpy as np
from PIL import Image
from sklearn.cluster import KMeans
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    HRFlowable, PageBreak, Image as RLImage,
)
from reportlab.graphics.shapes import Drawing, Rect, String
from reportlab.graphics import renderPDF

# ── Configurações

IMG_DIR = Path(__file__).parent.parent / "img"
OUTPUT_DIR = Path(__file__).parent.parent / "output"
NUM_COLORS = 6          # quantas cores extrair por imagem
THUMBNAIL_SIZE = (400, 400)
SUPPORTED_FORMATS = {".jpg", ".jpeg", ".png", ".bmp", ".gif", ".webp", ".tiff"}

# ── Funções auxiliares de cor

def rgb_to_hex(rgb: tuple) -> str:
    return "#{:02X}{:02X}{:02X}".format(*rgb)


def _luminance(rgb: tuple) -> float:
    r, g, b = [x / 255 for x in rgb]
    return 0.299 * r + 0.587 * g + 0.114 * b


def extract_dominant_colors(image_path: Path, n_colors: int = NUM_COLORS) -> list:
    """Retorna as cores dominantes da imagem, da mais para a menos presente."""
    img = Image.open(image_path).convert("RGBA")

    # troca pixels transparentes por branco
    background = Image.new("RGBA", img.size, (255, 255, 255, 255))
    background.paste(img, mask=img.split()[3])
    img_rgb = background.convert("RGB")

    # reduz o tamanho pra processar mais rápido
    img_rgb.thumbnail((200, 200), Image.LANCZOS)
    pixels = np.array(img_rgb).reshape(-1, 3).astype(float)

    # ignora pixels quase brancos (fundo)
    mask = ~np.all(pixels > 245, axis=1)
    filtered = pixels[mask]

    # se filtrou pixels demais, usa tudo
    if len(filtered) < n_colors:
        filtered = pixels

    k = min(n_colors, len(filtered))
    km = KMeans(n_clusters=k, n_init=10, random_state=42)
    km.fit(filtered)

    centers = km.cluster_centers_.astype(int)
    labels = km.labels_
    total = len(labels)

    counts = np.bincount(labels, minlength=k)
    order = np.argsort(-counts)

    result = []
    for idx in order:
        rgb = tuple(int(v) for v in np.clip(centers[idx], 0, 255))
        pct = counts[idx] / total * 100
        result.append({"rgb": rgb, "hex": rgb_to_hex(rgb), "pct": pct})
    return result


# ── Geração do PDF ───────────────────────────────────────────────────────────

PAGE_W, PAGE_H = A4
MARGIN = 2 * cm


def _swatch_drawing(rgb: tuple, width: float, height: float) -> Drawing:
    d = Drawing(width, height)
    d.add(Rect(
        0, 0, width, height,
        fillColor=colors.Color(rgb[0] / 255, rgb[1] / 255, rgb[2] / 255),
        strokeColor=colors.Color(0.8, 0.8, 0.8),
        strokeWidth=0.5,
    ))
    return d


def _color_card(rgb: tuple, card_w: float, card_h: float) -> Drawing:
    lum = _luminance(rgb)
    text_hex = "#FFFFFF" if lum < 0.5 else "#000000"
    d = Drawing(card_w, card_h)
    d.add(Rect(
        0, 0, card_w, card_h,
        fillColor=colors.Color(rgb[0] / 255, rgb[1] / 255, rgb[2] / 255),
        strokeWidth=0,
    ))
    d.add(String(
        card_w / 2, card_h - 18,
        "#{:02X}{:02X}{:02X}".format(*rgb),
        fontSize=9, fillColor=colors.HexColor(text_hex), textAnchor="middle",
    ))
    d.add(String(
        card_w / 2, 7,
        "R{}  G{}  B{}".format(*rgb),
        fontSize=7, fillColor=colors.HexColor(text_hex), textAnchor="middle",
    ))
    return d


def build_pdf(image_results: list, output_path: Path) -> None:
    doc = SimpleDocTemplate(
        str(output_path),
        pagesize=A4,
        leftMargin=MARGIN, rightMargin=MARGIN,
        topMargin=MARGIN, bottomMargin=MARGIN,
        title="Relatório de Paleta de Cores",
        author="Primary Colors Picker",
    )

    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        "ReportTitle", parent=styles["Title"],
        fontSize=28, textColor=colors.HexColor("#1A1A2E"),
        spaceAfter=6, alignment=TA_CENTER,
    )
    subtitle_style = ParagraphStyle(
        "Subtitle", parent=styles["Normal"],
        fontSize=11, textColor=colors.HexColor("#666666"),
        spaceAfter=4, alignment=TA_CENTER,
    )
    section_style = ParagraphStyle(
        "Section", parent=styles["Heading2"],
        fontSize=16, textColor=colors.HexColor("#1A1A2E"),
        spaceBefore=12, spaceAfter=8,
    )
    mono_style = ParagraphStyle(
        "Mono", parent=styles["Code"],
        fontSize=9, textColor=colors.HexColor("#222222"),
        alignment=TA_CENTER, leading=13,
    )
    label_style = ParagraphStyle(
        "Label", parent=styles["Normal"],
        fontSize=8, textColor=colors.HexColor("#555555"),
        alignment=TA_CENTER, leading=12,
    )
    note_style = ParagraphStyle(
        "Note", parent=styles["Normal"],
        fontSize=8, textColor=colors.HexColor("#888888"),
    )

    available_w = PAGE_W - 2 * MARGIN
    story = []

    # ── Capa ──────────────────────────────────────────────────────────────────
    story.append(Spacer(1, 3 * cm))
    story.append(Paragraph("Relatório de Paleta de Cores", title_style))
    story.append(Paragraph(
        datetime.now().strftime("Gerado em %d/%m/%Y às %H:%M"),
        subtitle_style,
    ))
    story.append(Paragraph(
        f"{len(image_results)} imagem(ns) analisada(s) &mdash; até {NUM_COLORS} cores por imagem",
        subtitle_style,
    ))
    story.append(Spacer(1, 1 * cm))
    story.append(HRFlowable(width="100%", thickness=2, color=colors.HexColor("#1A1A2E")))

    # faixa com todas as cores juntas
    all_colors = [c for entry in image_results for c in entry["colors"]]
    if all_colors:
        story.append(Spacer(1, 0.6 * cm))
        strip_cell_w = available_w / len(all_colors)
        strip_h = 1.4 * cm
        strip = Drawing(available_w, strip_h)
        for i, c in enumerate(all_colors):
            strip.add(Rect(
                i * strip_cell_w, 0, strip_cell_w, strip_h,
                fillColor=colors.Color(c["rgb"][0] / 255, c["rgb"][1] / 255, c["rgb"][2] / 255),
                strokeWidth=0,
            ))
        story.append(strip)
        story.append(Spacer(1, 0.2 * cm))
        story.append(Paragraph("Paleta combinada de todas as imagens", note_style))

    story.append(PageBreak())

    # ── Seção por imagem ──────────────────────────────────────────────────────
    swatch_h = 3.0 * cm
    card_h = 1.8 * cm

    for entry in image_results:
        palette = entry["colors"]
        n = len(palette)
        col_w = available_w / n

        story.append(Paragraph(entry["name"], section_style))
        story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#CCCCCC")))
        story.append(Spacer(1, 0.4 * cm))

        # miniatura da imagem
        with Image.open(entry["path"]) as thumb:
            thumb.thumbnail(THUMBNAIL_SIZE, Image.LANCZOS)
            thumb_w, thumb_h = thumb.size

        max_display_w = available_w * 0.55
        max_display_h = 7 * cm
        scale = min(max_display_w / thumb_w, max_display_h / thumb_h)
        display_w = thumb_w * scale
        display_h = thumb_h * scale

        story.append(RLImage(str(entry["path"]), width=display_w, height=display_h))
        story.append(Spacer(1, 0.6 * cm))

        # linha de amostras de cor
        swatch_row = [_swatch_drawing(c["rgb"], col_w - 4, swatch_h) for c in palette]
        hex_row = [Paragraph(c["hex"], mono_style) for c in palette]
        rgb_row = [Paragraph("rgb({}, {}, {})".format(*c["rgb"]), label_style) for c in palette]
        pct_row = [Paragraph("{:.1f}%".format(c["pct"]), label_style) for c in palette]

        tbl = Table(
            [swatch_row, hex_row, rgb_row, pct_row],
            colWidths=[col_w] * n,
            rowHeights=[swatch_h + 2, 16, 14, 14],
        )
        tbl.setStyle(TableStyle([
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 2),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
            ("LEFTPADDING", (0, 0), (-1, -1), 2),
            ("RIGHTPADDING", (0, 0), (-1, -1), 2),
        ]))
        story.append(tbl)
        story.append(Spacer(1, 0.6 * cm))

        # cards compactos com HEX e RGB
        card_row = [_color_card(c["rgb"], col_w - 6, card_h) for c in palette]
        card_tbl = Table(
            [card_row],
            colWidths=[col_w] * n,
            rowHeights=[card_h + 4],
        )
        card_tbl.setStyle(TableStyle([
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING", (0, 0), (-1, -1), 3),
            ("RIGHTPADDING", (0, 0), (-1, -1), 3),
        ]))
        story.append(card_tbl)
        story.append(PageBreak())

    doc.build(story)


# ── Execução via terminal ─────────────────────────────────────────────────────

def run() -> None:
    if not IMG_DIR.exists():
        print(f"[ERRO] Pasta de imagens não encontrada: {IMG_DIR}")
        sys.exit(1)

    images = sorted([
        p for p in IMG_DIR.iterdir()
        if p.suffix.lower() in SUPPORTED_FORMATS and p.is_file()
    ])

    if not images:
        print(f"[INFO] Nenhuma imagem encontrada em {IMG_DIR}")
        print(f"       Coloque os logos aqui e rode novamente.")
        print(f"       Formatos aceitos: {', '.join(sorted(SUPPORTED_FORMATS))}")
        sys.exit(0)

    print(f"[INFO] {len(images)} imagem(ns) encontrada(s)")

    image_results = []
    for img_path in images:
        print(f"  > {img_path.name} ...", end=" ", flush=True)
        try:
            palette = extract_dominant_colors(img_path)
            image_results.append({"name": img_path.stem, "path": img_path, "colors": palette})
            print("OK")
            for c in palette:
                print(f"       {c['hex']}  rgb{c['rgb']}  {c['pct']:.1f}%")
        except Exception as exc:
            print(f"IGNORADO — {exc}")

    if not image_results:
        print("[ERRO] Nenhuma imagem processada com sucesso.")
        sys.exit(1)

    OUTPUT_DIR.mkdir(exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = OUTPUT_DIR / f"color_palette_{timestamp}.pdf"

    print(f"\n[INFO] Gerando PDF ...")
    build_pdf(image_results, output_path)
    print(f"[DONE] {output_path}")


if __name__ == "__main__":
    run()
