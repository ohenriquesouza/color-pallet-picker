"""
Interface web do Primary Colors Picker.
Para rodar: streamlit run src/app.py
"""

import sys
import json
import tempfile
from pathlib import Path
from datetime import datetime

import streamlit as st
from PIL import Image as PILImage

sys.path.insert(0, str(Path(__file__).parent))
from main import extract_dominant_colors, build_pdf, IMG_DIR, OUTPUT_DIR

# ── Configuração da página ────────────────────────────────────────────────────

st.set_page_config(
    page_title="Primary Colors Picker",
    page_icon="🎨",
    layout="wide",
    initial_sidebar_state="expanded",
)

# botão de abrir/fechar sidebar sempre visível, em qualquer tema
st.markdown("""
<style>
/* Botão ">>" para reabrir o sidebar quando fechado */
[data-testid="collapsedControl"] {
    display: flex !important;
    visibility: visible !important;
    opacity: 1 !important;
    background-color: #1a1a2e !important;
    border-radius: 0 10px 10px 0 !important;
    padding: 10px 6px !important;
    top: 50% !important;
    transform: translateY(-50%) !important;
    box-shadow: 2px 2px 8px rgba(0,0,0,0.25) !important;
    transition: background-color 0.2s ease !important;
}
[data-testid="collapsedControl"]:hover {
    background-color: #2d2d4e !important;
}
[data-testid="collapsedControl"] svg {
    fill: #ffffff !important;
    color: #ffffff !important;
}

/* Botão "<<" para fechar o sidebar quando aberto */
[data-testid="stSidebarCollapseButton"] button,
section[data-testid="stSidebar"] button[kind="header"] {
    background-color: transparent !important;
    color: #1a1a2e !important;
    border: 1.5px solid rgba(26,26,46,0.25) !important;
    border-radius: 8px !important;
    opacity: 1 !important;
    visibility: visible !important;
}
[data-testid="stSidebarCollapseButton"] button:hover,
section[data-testid="stSidebar"] button[kind="header"]:hover {
    background-color: rgba(26,26,46,0.08) !important;
}
[data-testid="stSidebarCollapseButton"] svg,
section[data-testid="stSidebar"] button[kind="header"] svg {
    fill: #1a1a2e !important;
    color: #1a1a2e !important;
}
</style>
""", unsafe_allow_html=True)

# ── Funções auxiliares ────────────────────────────────────────────────────────

def _lighten(rgb: tuple, factor: float = 0.88) -> str:
    """Clareia uma cor misturando com branco."""
    r, g, b = (int(c + (255 - c) * factor) for c in rgb)
    return "#{:02X}{:02X}{:02X}".format(r, g, b)


def _lum(rgb: tuple) -> float:
    r, g, b = [x / 255 for x in rgb]
    return 0.299 * r + 0.587 * g + 0.114 * b


def _text_on(rgb: tuple) -> str:
    return "#ffffff" if _lum(rgb) < 0.5 else "#111111"


def group_colors(palette: list) -> tuple[list, list, list]:
    """Agrupa as cores em primárias, secundárias e destaques pela % de presença."""
    primary, secondary, accent = [], [], []
    for i, c in enumerate(palette):
        if i == 0 or c["pct"] >= 20:
            primary.append(c)
        elif c["pct"] >= 8:
            secondary.append(c)
        else:
            accent.append(c)
    return primary, secondary, accent


def palette_html(palette: list, primary: list, secondary: list, accent: list) -> str:
    """Gera o HTML dos cards de cores clicáveis."""

    def cards(colors: list, swatch_h: int) -> str:
        out = ""
        for c in colors:
            bg = "rgb({},{},{})".format(*c["rgb"])
            fg = _text_on(c["rgb"])
            bar_w = min(100, round(c["pct"] * 2))  # barra proporcional à dominância
            out += f"""
            <div class="card" onclick="copy('{c['hex']}')">
                <div class="swatch" style="background:{bg}; height:{swatch_h}px;">
                    <span class="swatch-hex" style="color:{fg};">{c['hex']}</span>
                </div>
                <div class="info">
                    <div class="hex">{c['hex']}</div>
                    <div class="rgb">rgb({c['rgb'][0]}, {c['rgb'][1]}, {c['rgb'][2]})</div>
                    <div class="pct">{c['pct']:.1f}% da imagem</div>
                    <div class="bar-bg">
                        <div class="bar" style="width:{bar_w}%; background:{bg};"></div>
                    </div>
                </div>
            </div>"""
        return out

    def section(title: str, colors: list, swatch_h: int) -> str:
        if not colors:
            return ""
        return f"""
        <div class="section">
            <div class="section-title">{title}</div>
            <div class="grid">{cards(colors, swatch_h)}</div>
        </div>"""

    sections = (
        section("Cores Primárias", primary, 160)
        + section("Cores Secundárias", secondary, 120)
        + section("Cores de Destaque / Acento", accent, 96)
    )

    n_sections = sum([bool(primary), bool(secondary), bool(accent)])
    height = n_sections * 270 + 60

    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: transparent; }}

  .section {{ margin-bottom: 28px; }}
  .section-title {{
    font-size: 13px;
    font-weight: 700;
    letter-spacing: 1.2px;
    text-transform: uppercase;
    color: #888;
    margin-bottom: 12px;
  }}

  .grid {{
    display: flex;
    flex-wrap: wrap;
    gap: 14px;
  }}

  .card {{
    cursor: pointer;
    border-radius: 14px;
    overflow: hidden;
    box-shadow: 0 2px 12px rgba(0,0,0,0.10);
    width: 150px;
    transition: transform .18s ease, box-shadow .18s ease;
    background: #fff;
    user-select: none;
  }}
  .card:hover {{
    transform: translateY(-6px);
    box-shadow: 0 10px 28px rgba(0,0,0,0.18);
  }}
  .card:active {{ transform: translateY(-3px); }}

  .swatch {{
    display: flex;
    align-items: flex-end;
    justify-content: center;
    padding-bottom: 8px;
  }}
  .swatch-hex {{
    font-family: monospace;
    font-size: 11px;
    font-weight: 600;
    opacity: 0;
    transition: opacity .18s;
    background: rgba(0,0,0,0.18);
    padding: 2px 6px;
    border-radius: 4px;
  }}
  .card:hover .swatch-hex {{ opacity: 1; }}

  .info {{
    padding: 10px 12px 12px;
    border-top: 1px solid rgba(0,0,0,0.06);
  }}
  .hex {{
    font-family: 'Courier New', monospace;
    font-size: 13px;
    font-weight: 700;
    color: #1a1a2e;
    letter-spacing: .5px;
  }}
  .rgb {{ font-size: 10px; color: #999; margin-top: 3px; }}
  .pct {{ font-size: 10px; color: #bbb; margin-top: 2px; }}
  .bar-bg {{ height: 3px; background: #f0f0f0; border-radius: 2px; margin-top: 7px; overflow: hidden; }}
  .bar    {{ height: 100%; border-radius: 2px; transition: width .4s ease; }}

  /* Toast */
  #toast {{
    position: fixed;
    bottom: 24px;
    left: 50%;
    transform: translateX(-50%) translateY(70px);
    background: #1a1a2e;
    color: #fff;
    padding: 10px 22px;
    border-radius: 30px;
    font-family: monospace;
    font-size: 13px;
    font-weight: 600;
    transition: transform .28s cubic-bezier(.34,1.56,.64,1);
    pointer-events: none;
    z-index: 9999;
    white-space: nowrap;
  }}
  #toast.show {{ transform: translateX(-50%) translateY(0); }}
</style>
</head>
<body>
  <div id="toast">copiado!</div>
  {sections}
  <script>
  function copy(hex) {{
    const cb = () => {{
      const t = document.getElementById('toast');
      t.textContent = hex + ' copiado!';
      t.classList.add('show');
      clearTimeout(window._tt);
      window._tt = setTimeout(() => t.classList.remove('show'), 1800);
    }};
    if (navigator.clipboard) {{
      navigator.clipboard.writeText(hex).then(cb).catch(() => fallback(hex, cb));
    }} else {{ fallback(hex, cb); }}
  }}
  function fallback(hex, cb) {{
    const el = document.createElement('textarea');
    el.value = hex; el.style.position = 'fixed'; el.style.opacity = '0';
    document.body.appendChild(el); el.focus(); el.select();
    try {{ document.execCommand('copy'); }} catch(e) {{}}
    document.body.removeChild(el);
    cb();
  }}
  </script>
</body>
</html>""", height


# ── Barra lateral ────────────────────────────────────────────────────────────

with st.sidebar:
    st.markdown("## 🎨 Primary Colors Picker")
    st.caption("Extrator de cores dominantes para personalização do seu projeto escalável.")
    st.divider()

    source = st.radio("Fonte da imagem", ["Upload"])

    image_path: Path | None = None
    image_name: str = "logo"

    if source == "Upload":
        uploaded = st.file_uploader(
            "Solte seu logo aqui",
            type=["png", "jpg", "jpeg", "webp", "bmp", "gif", "tiff"],
        )
        if uploaded:
            suffix = Path(uploaded.name).suffix
            tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
            tmp.write(uploaded.read())
            tmp.close()
            image_path = Path(tmp.name)
            image_name = Path(uploaded.name).stem
    # else:
    #     exts = {".jpg", ".jpeg", ".png", ".bmp", ".gif", ".webp", ".tiff"}
    #     img_files = (
    #         sorted([p for p in IMG_DIR.iterdir() if p.suffix.lower() in exts and p.is_file()])
    #         if IMG_DIR.exists() else []
    #     )
    #     if img_files:
    #         sel = st.selectbox("Escolha uma imagem", img_files, format_func=lambda p: p.name)
    #         image_path = sel
    #         image_name = sel.stem
    #     else:
    #         st.warning("Nenhuma imagem encontrada em `img/`.")

    st.divider()
    n_colors = st.slider("Número de cores a extrair", min_value=3, max_value=10, value=3, key="n_colors_slider")
    st.divider()
    st.caption("Clique em qualquer card ou código HEX para copiar para a área de transferência.")


# ── Conteúdo principal ───────────────────────────────────────────────────────

st.markdown("# 🎨 Primary Colors Picker")
st.caption("Extrator de cores dominantes para personalização do seu projeto escalável")

if image_path is None:
    st.info("Selecione ou faça upload de uma logo no painel lateral para começar.")
    st.stop()

# extrai as cores da imagem
with st.spinner("Analisando cores..."):
    try:
        palette = extract_dominant_colors(image_path, n_colors=n_colors)
    except Exception as exc:
        st.error(f"Erro ao processar imagem: {exc}")
        st.stop()

# ── Imagem e strip de cores ───────────────────────────────────────────────────

col_img, col_right = st.columns([1, 2], gap="large")

with col_img:
    img = PILImage.open(image_path)
    img.thumbnail((280, 280), PILImage.LANCZOS)
    st.image(img, caption=image_name, use_container_width=False)

with col_right:
    st.markdown("**Paleta completa** — proporcional à dominância")

    # faixa de cores proporcional à dominância
    strip_parts = "".join(
        f'<div title="{c["hex"]} ({c["pct"]:.1f}%)" '
        f'style="flex:{c["pct"]:.2f}; background:rgb({c["rgb"][0]},{c["rgb"][1]},{c["rgb"][2]});"></div>'
        for c in palette
    )
    st.markdown(
        f'<div style="display:flex; height:52px; border-radius:10px; overflow:hidden; '
        f'box-shadow:0 2px 10px rgba(0,0,0,0.12); margin-bottom:14px;">{strip_parts}</div>',
        unsafe_allow_html=True,
    )

    # pills com os códigos HEX
    pills = " ".join(
        f'<span style="display:inline-block; background:rgb({c["rgb"][0]},{c["rgb"][1]},{c["rgb"][2]}); '
        f'color:{_text_on(c["rgb"])}; padding:4px 13px; border-radius:20px; '
        f'font-family:monospace; font-size:13px; font-weight:600; margin:3px 2px; '
        f'letter-spacing:.5px;">{c["hex"]}</span>'
        for c in palette
    )
    st.markdown(pills, unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    # métricas rápidas
    metric_cols = st.columns(3)
    metric_cols[0].metric("Cores extraídas", len(palette))
    metric_cols[1].metric("Cor dominante", palette[0]["hex"])
    metric_cols[2].metric("Dominância", f"{palette[0]['pct']:.0f}%")

st.divider()

# ── Cards de cores interativos ───────────────────────────────────────────────

primary, secondary, accent = group_colors(palette)
html_content, height = palette_html(palette, primary, secondary, accent)
st.components.v1.html(html_content, height=height, scrolling=False)

st.divider()

# ── Exportar PDF ─────────────────────────────────────────────────────────────

st.markdown("### Exportar")
col_exp, col_info = st.columns([1, 2])

with col_exp:
    if st.button("📄 Gerar PDF", type="primary", use_container_width=True):
        with st.spinner("Gerando PDF..."):
            OUTPUT_DIR.mkdir(exist_ok=True)
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            pdf_path = OUTPUT_DIR / f"palette_{image_name}_{ts}.pdf"
            build_pdf([{"name": image_name, "path": image_path, "colors": palette}], pdf_path)

        with open(pdf_path, "rb") as f:
            pdf_bytes = f.read()

        st.download_button(
            "⬇️ Baixar PDF",
            data=pdf_bytes,
            file_name=pdf_path.name,
            mime="application/pdf",
            use_container_width=True,
        )

with col_info:
    st.caption(
        "O PDF inclui capa com a paleta combinada, thumbnail da logo, "
        "swatches com HEX, RGB e % de dominância para cada cor."
    )

st.divider()

# ── Snippets prontos para o projeto ──────────────────────────────────────────

st.markdown("### 🖥️ Código para Projeto")
st.caption(
    "Snippets prontos para colar no seu projeto Streamlit. "
    "No futuro, essa etapa pode ser automatizada assim que o cliente fizer upload da logo."
)

client_slug = image_name.lower().replace(" ", "_").replace("-", "_")
p_color  = primary[0]["hex"]
p_rgb    = primary[0]["rgb"]
s_color  = secondary[0]["hex"] if secondary else (primary[1]["hex"] if len(primary) > 1 else p_color)
a_color  = accent[0]["hex"] if accent else s_color
bg_light = _lighten(p_rgb, factor=0.92)
text_on_primary = _text_on(p_rgb)

tab_css, tab_toml, tab_py, tab_json = st.tabs(["CSS Variables", "config.toml", "Python", "JSON"])

# ── Aba CSS ──────────────────────────────────────────────────────────────────
with tab_css:
    st.caption("Cole no CSS do seu `set_custom_header` ou em qualquer `st.markdown(..., unsafe_allow_html=True)`.")

    css_snippet = f"""\
/* ── Cliente: {image_name} ── */
:root {{
    --brand-primary:         {p_color};   /* {primary[0]['pct']:.1f}% */
    --brand-secondary:       {s_color};
    --brand-accent:          {a_color};
    --brand-bg-tint:         {bg_light};
    --brand-text-on-primary: {text_on_primary};
}}"""

    st.code(css_snippet, language="css")
    st.download_button(
        "⬇️ Baixar .css",
        data=css_snippet,
        file_name=f"theme_{client_slug}.css",
        mime="text/css",
    )

# ── Aba config.toml ──────────────────────────────────────────────────────────
with tab_toml:
    st.caption("Salve como `.streamlit/config.toml` na raiz do projeto do cliente.")

    toml_snippet = f"""\
[theme]
primaryColor      = "{p_color}"
backgroundColor   = "#FFFFFF"
secondaryBackgroundColor = "{bg_light}"
textColor         = "#111111"
font              = "sans serif"
"""

    st.code(toml_snippet, language="toml")
    st.download_button(
        "⬇️ Baixar config.toml",
        data=toml_snippet,
        file_name="config.toml",
        mime="text/plain",
    )

# ── Aba Python ───────────────────────────────────────────────────────────────
with tab_py:
    st.caption("Cole no `app.py` do projeto — lógica de seleção de tema por cliente.")

    all_colors_py = "\n".join(
        f'    "{c["hex"]}",  # {c["pct"]:.1f}%'
        for c in palette
    )

    py_snippet = f"""\
import streamlit as st

# ── Paleta extraída automaticamente da logo ───────────────────────────────────
PALETTE_{client_slug.upper()} = {{
    "primary":   "{p_color}",
    "secondary": "{s_color}",
    "accent":    "{a_color}",
    "bg_tint":   "{bg_light}",
    "all": [
{all_colors_py}
    ],
}}

# ── Seleção de tema por cliente ───────────────────────────────────────────────
current_username = st.session_state.get("username", "")
if current_username == "{client_slug}":
    st.session_state["header_filter"] = "{client_slug}"

header_partner = st.session_state.get("header_filter", "default") or "default"

set_custom_header(
    f"data/header_{{header_partner}}.png",
    header_height=120,
    margin_top=180,
)
"""

    st.code(py_snippet, language="python")
    st.download_button(
        "⬇️ Baixar .py",
        data=py_snippet,
        file_name=f"theme_{client_slug}.py",
        mime="text/plain",
    )

# ── Aba JSON ─────────────────────────────────────────────────────────────────
with tab_json:
    st.caption("Paleta estruturada para integração futura com o sistema de temas do cliente.")

    palette_dict = {
        "client": client_slug,
        "source_image": image_name,
        "extracted_at": datetime.now().isoformat(timespec="seconds"),
        "streamlit_theme": {
            "primaryColor": p_color,
            "backgroundColor": "#FFFFFF",
            "secondaryBackgroundColor": bg_light,
            "textColor": "#111111",
        },
        "colors": {
            "primary":   [{"hex": c["hex"], "rgb": list(c["rgb"]), "pct": round(c["pct"], 2)} for c in primary],
            "secondary": [{"hex": c["hex"], "rgb": list(c["rgb"]), "pct": round(c["pct"], 2)} for c in secondary],
            "accent":    [{"hex": c["hex"], "rgb": list(c["rgb"]), "pct": round(c["pct"], 2)} for c in accent],
        },
    }
    palette_json_str = json.dumps(palette_dict, indent=2, ensure_ascii=False)

    st.json(palette_dict)
    st.download_button(
        "⬇️ Baixar JSON",
        data=palette_json_str,
        file_name=f"palette_{client_slug}.json",
        mime="application/json",
    )
