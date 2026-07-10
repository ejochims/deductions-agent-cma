"""Visual system for the UI — one place for color, chrome, chips, and charts.

All values come from a validated reference palette (CVD-checked ordering,
status colors distinct from series colors, warm-neutral surfaces). app.py
renders against these roles; nothing else in the repo knows about hex codes.
"""

from __future__ import annotations

import altair as alt

# ---------------------------------------------------------------- palette roles
INK = "#16150f"            # primary ink (matches docs/presentation.html tokens)
INK_2 = "#52514e"          # secondary ink
MUTED = "#8a8880"          # axis / captions
SURFACE = "#fdfdfc"        # card surface
PLANE = "#f4f3ee"          # page plane
HAIRLINE = "#e2e1da"       # gridline / borders
ACCENT = "#2a78d6"         # blue (categorical slot 1) — the one accent hue
ACCENT_DEEP = "#1c5cab"

# Status palette (reserved; never used as series colors). Each chip pairs the
# color with a label — color never carries meaning alone.
STATUS = {
    "good": "#0ca30c",
    "warning": "#fab219",
    "serious": "#ec835a",
    "critical": "#d03b3b",
}

# Settlement actions -> (label, chip style). partial uses a darkened warning
# text tone for legibility on the light tint.
ACTION_CHIP = {
    "approve": ("APPROVE", "#0ca30c", "#eaf6ea", "#006300"),
    "deny": ("DENY", "#d03b3b", "#fbeaea", "#a02020"),
    "partial": ("PARTIAL", "#fab219", "#fdf3dd", "#7a5200"),
    "escalate": ("ESCALATE", "#4a3aa7", "#edeafa", "#3a2d85"),
}

BUCKET_TINT = {
    "approve": "#006300", "deny": "#a02020", "partial": "#7a5200",
    "escalate": "#3a2d85", "ambiguous": "#52514e", "memory": "#1c5cab",
}


BUCKET_ORDER = ["approve", "deny", "partial", "escalate", "ambiguous", "memory"]


def money(value: float, decimals: int = 2) -> str:
    """Dollar amount safe for HTML-in-markdown (a literal `$` next to another
    `$` triggers Streamlit's LaTeX-math parsing and garbles the string)."""
    return f"&#36;{value:,.{decimals}f}"


def esc_md(text: str) -> str:
    """Escape `$` in prose so markdown never interprets it as math."""
    return text.replace("$", "\\$")


def chip(text: str, fg: str, bg: str, border: str | None = None) -> str:
    """A small rounded status chip (inline HTML)."""
    b = border or fg
    return (
        f'<span style="display:inline-block;padding:2px 10px;border-radius:999px;'
        f'font-size:0.72rem;font-weight:600;letter-spacing:.04em;'
        f'color:{fg};background:{bg};border:1px solid {b}22;">{text}</span>'
    )


def action_chip(action: str) -> str:
    label, _dot, bg, fg = ACTION_CHIP.get(
        action, (action.upper(), MUTED, "#f0efec", INK_2))
    return chip(label, fg, bg)


def check_chip(name: str, passed: bool, applicable: bool) -> str:
    if not applicable:
        return chip(f"— {name}", INK_2, "#f0efec")
    if passed:
        return chip(f"✓ {name}", "#006300", "#eaf6ea")
    return chip(f"✕ {name}", "#a02020", "#fbeaea")


# ----------------------------------------------------------------------- CSS
CSS = f"""
<style>
/* chrome: hide streamlit's menu/footer/deploy for an app-like feel */
#MainMenu, footer, [data-testid="stToolbar"] {{ visibility: hidden; height: 0; }}

/* page rhythm */
.block-container {{ max-width: 1180px; padding-top: 2.2rem; padding-bottom: 4rem; }}

/* type scale — editorial serif headings, echoing the deck's display face */
h1 {{ font-family: Georgia, 'Times New Roman', serif !important;
     font-weight: 700 !important; letter-spacing: -0.015em !important;
     font-size: 2.05rem !important; color: {INK} !important; }}
h2, h3 {{ font-family: Georgia, 'Times New Roman', serif !important;
          font-weight: 650 !important; letter-spacing: -0.01em !important;
          color: {INK} !important; }}
[data-testid="stCaptionContainer"] p {{ color: {INK_2}; }}

/* metric tiles -> cards */
[data-testid="stMetric"] {{
  background: {SURFACE}; border: 1px solid {HAIRLINE}; border-radius: 12px;
  padding: 14px 16px 12px 16px;
  box-shadow: inset 0 1px 0 rgba(255,255,255,.85),
              0 1px 2px rgba(22,21,15,.03), 0 10px 28px -18px rgba(22,21,15,.16);
}}
[data-testid="stMetricLabel"] p {{ color: {MUTED}; font-size: 0.78rem;
  font-weight: 600; letter-spacing: .05em; text-transform: uppercase; }}
[data-testid="stMetricValue"] {{ color: {INK}; font-weight: 700; }}

/* tabs: quieter bar, stronger active state */
[data-testid="stTabs"] [data-baseweb="tab-list"] {{ gap: 4px; border-bottom: 1px solid {HAIRLINE}; }}
[data-testid="stTabs"] [data-baseweb="tab"] {{ padding: 10px 14px; font-weight: 600; color: {INK_2}; }}
[data-testid="stTabs"] [aria-selected="true"] {{ color: {ACCENT_DEEP}; }}

/* expanders as cards */
[data-testid="stExpander"] {{
  background: {SURFACE}; border: 1px solid {HAIRLINE}; border-radius: 10px;
}}

/* dataframes: hairline ring */
[data-testid="stDataFrame"] {{ border: 1px solid {HAIRLINE}; border-radius: 10px; }}

/* code blocks (remittance text) on the warm surface */
[data-testid="stCode"] {{ border: 1px solid {HAIRLINE}; border-radius: 10px; }}

/* dividers lighter */
hr {{ border-color: {HAIRLINE}; }}
</style>
"""


# --------------------------------------------------------------------- charts
def bucket_bar(rows: list[dict], value_key: str = "pass^k") -> alt.Chart:
    """pass^k by bucket — single-hue thin bars, rounded data ends, hairline grid,
    direct value labels, tooltip on hover. One series, so no legend."""
    by_bucket = {r["bucket"]: r for r in rows if r["bucket"] != "OVERALL"}
    data = [
        {"bucket": b,
         "value": (by_bucket[b].get(value_key)
                   if by_bucket[b].get(value_key) is not None else 0.0),
         "cases": by_bucket[b].get("cases", 0)}
        for b in BUCKET_ORDER if b in by_bucket
    ]
    base = alt.Chart(alt.Data(values=data))
    bars = base.mark_bar(
        size=26, cornerRadiusTopLeft=4, cornerRadiusTopRight=4, color=ACCENT,
    ).encode(
        x=alt.X("bucket:N", sort=None, axis=alt.Axis(
            labelAngle=0, labelColor=MUTED, title=None, domainColor=HAIRLINE,
            tickColor=HAIRLINE)),
        y=alt.Y("value:Q", scale=alt.Scale(domain=[0, 1]), axis=alt.Axis(
            title=value_key, titleColor=MUTED, labelColor=MUTED, format=".0%",
            gridColor=HAIRLINE, domainOpacity=0, tickOpacity=0)),
        tooltip=[alt.Tooltip("bucket:N"), alt.Tooltip("value:Q", format=".0%"),
                 alt.Tooltip("cases:Q", title="cases")],
    )
    labels = base.mark_text(
        dy=-8, color=INK_2, fontWeight=600, fontSize=12,
    ).encode(
        x=alt.X("bucket:N", sort=None),
        y=alt.Y("value:Q", scale=alt.Scale(domain=[0, 1])),
        text=alt.Text("value:Q", format=".0%"),
    )
    return (bars + labels).properties(height=240, background="transparent").configure_view(
        strokeOpacity=0)
