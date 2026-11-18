"""Design tokens + global CSS. Two palettes (dark / light); every colour is a CSS variable so the
whole UI follows the active Streamlit theme (st.context.theme.type)."""
from __future__ import annotations

import html

import streamlit as st

PALETTES = {
    "dark": {
        "bg": "#0A0D1F", "surface": "#121834", "surface2": "#1A2148", "border": "rgba(139,148,220,0.18)",
        "text": "#F5F3FF", "muted": "#A5ACD0", "primary": "#FF4F8B", "secondary": "#8B5CF6", "cyan": "#22D3EE",
        "success": "#10B981", "warning": "#FBBF24", "danger": "#F43F5E", "fuchsia": "#E879F9", "blue": "#60A5FA",
        "header": "rgba(10,13,31,0.62)", "sidebar1": "#161C3D", "sidebar2": "#0E1330",
        "title1": "#FF8FB1", "title2": "#C4B5FD", "title3": "#67E8F9", "title4": "#6EE7B7",
        "glow": "0.30", "surface_alpha": "rgba(18,24,52,0.72)", "grid": "rgba(165,172,208,0.12)",
        "accent-hue": "-15deg", "accent-sat": "1.05",
    },
    # calm, neutral light mode: slate greys, white surfaces, one indigo accent, muted status colours
    "light": {
        "bg": "#F7F8FB", "surface": "#FFFFFF", "surface2": "#F3F4F7", "border": "#E3E6EC",
        "text": "#111827", "muted": "#5B6474", "primary": "#4F46E5", "secondary": "#6D5BD0", "cyan": "#0E7490",
        "success": "#15803D", "warning": "#B45309", "danger": "#B91C1C", "fuchsia": "#7C6FD6", "blue": "#2563EB",
        "header": "rgba(255,255,255,0.88)", "sidebar1": "#FFFFFF", "sidebar2": "#FFFFFF",
        "title1": "#111827", "title2": "#111827", "title3": "#111827", "title4": "#111827",
        "glow": "0", "surface_alpha": "#FFFFFF", "grid": "rgba(17,24,39,0.07)",
        "accent-hue": "243deg", "accent-sat": "0.85",
    },
}

# Live palette used by components at render time (updated in place by inject()).
C: dict[str, str] = dict(PALETTES["dark"])

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&family=JetBrains+Mono:wght@500&display=swap');
html, body, [class*="css"], .stMarkdown, .stText, button, input, textarea, select {
  font-family: 'Inter', system-ui, -apple-system, sans-serif !important; }

.stApp { background:
    radial-gradient(1100px 640px at 6% -14%, color-mix(in srgb, var(--secondary) calc(var(--glow) * 100%), transparent), transparent 62%),
    radial-gradient(950px 600px at 104% -6%, color-mix(in srgb, var(--primary) calc(var(--glow) * 85%), transparent), transparent 60%),
    radial-gradient(850px 520px at 55% 118%, color-mix(in srgb, var(--cyan) calc(var(--glow) * 60%), transparent), transparent 62%),
    radial-gradient(600px 400px at -5% 80%, color-mix(in srgb, var(--fuchsia) calc(var(--glow) * 45%), transparent), transparent 60%),
    var(--bg);
  background-attachment: fixed; color: var(--text); }

/* top bar: frosted glass + animated gradient line; content always starts below it */
header[data-testid="stHeader"] { background: var(--header); backdrop-filter: blur(16px) saturate(150%);
  -webkit-backdrop-filter: blur(16px) saturate(150%); border-bottom: 1px solid var(--border); }
header[data-testid="stHeader"]::after { content:""; position:absolute; left:0; right:0; bottom:-1px; height:3px;
  background: linear-gradient(90deg, var(--primary), var(--fuchsia), var(--secondary), var(--cyan), var(--success), var(--warning), var(--primary));
  background-size: 300% 100%; animation: kp-flow 9s linear infinite; }
@keyframes kp-flow { 0% { background-position: 0% 50%; } 100% { background-position: 300% 50%; } }
.block-container { padding-top: 4.6rem !important; padding-bottom: 4rem; max-width: 1280px; }

/* sidebar */
section[data-testid="stSidebar"] { background: linear-gradient(180deg, var(--sidebar1) 0%, var(--sidebar2) 100%);
  border-right: 1px solid var(--border); }
section[data-testid="stSidebar"] [data-testid="stSidebarNav"] a { border-radius: 11px; margin: 3px 0; transition: all .15s ease; }
section[data-testid="stSidebar"] [data-testid="stSidebarNav"] a:hover { background: color-mix(in srgb, var(--secondary) 14%, transparent); }
section[data-testid="stSidebar"] [data-testid="stSidebarNav"] a[aria-current="page"] {
  background: linear-gradient(90deg, color-mix(in srgb, var(--primary) 30%, transparent), color-mix(in srgb, var(--secondary) 18%, transparent));
  box-shadow: inset 3px 0 0 var(--primary), 0 8px 22px -10px color-mix(in srgb, var(--primary) 70%, transparent); }
section[data-testid="stSidebar"] [data-testid="stSidebarNav"] a span { font-weight: 560; }
.kp-brand { font-weight: 900; font-size: 1.25rem; letter-spacing: -.03em; color: var(--text); }
.kp-brand span { background: linear-gradient(90deg, var(--primary), var(--secondary), var(--cyan));
  -webkit-background-clip: text; -webkit-text-fill-color: transparent; }
.kp-brand-sub { color: var(--muted); font-size: .8rem; margin-bottom: .6rem; }

h1, h2, h3, h4 { letter-spacing: -0.02em; }
h4 { background: linear-gradient(90deg, var(--text), var(--secondary) 70%, var(--cyan));
  -webkit-background-clip: text; -webkit-text-fill-color: transparent; }
hr { border-color: var(--border); }

/* hero */
.kp-hero { position: relative; overflow: hidden; display:flex; align-items:center; justify-content:space-between; gap:1rem;
  flex-wrap:wrap; padding: 1.6rem 1.8rem; border-radius: 22px; border: 1px solid var(--border); margin-bottom: 1.2rem;
  background:
    radial-gradient(420px 220px at 92% -30%, color-mix(in srgb, var(--cyan) 30%, transparent), transparent 70%),
    radial-gradient(380px 240px at 0% 120%, color-mix(in srgb, var(--fuchsia) 26%, transparent), transparent 70%),
    linear-gradient(125deg, color-mix(in srgb, var(--primary) 22%, transparent), color-mix(in srgb, var(--secondary) 18%, transparent) 55%, var(--surface_alpha));
  box-shadow: 0 24px 60px -30px color-mix(in srgb, var(--secondary) 80%, transparent); }
.kp-hero h1 { margin:0; font-size: 2.55rem; font-weight: 900; padding: 0;
  background: linear-gradient(90deg, var(--title1), var(--title2), var(--title3), var(--title4), var(--title1));
  background-size: 250% 100%; animation: kp-flow 12s linear infinite;
  -webkit-background-clip: text; -webkit-text-fill-color: transparent;
  filter: drop-shadow(0 4px 24px color-mix(in srgb, var(--primary) 35%, transparent)); }
.kp-hero p { margin: .3rem 0 0; color: var(--muted); font-size: 1rem; }

/* page headers */
.kp-page-head { position: relative; overflow: hidden; padding: 1.2rem 1.4rem 1.15rem 1.7rem; margin: 0 0 1.2rem;
  border-radius: 20px; border: 1px solid color-mix(in srgb, var(--secondary) 28%, transparent);
  background: linear-gradient(118deg, color-mix(in srgb, var(--primary) 18%, transparent) 0%,
              color-mix(in srgb, var(--secondary) 16%, transparent) 48%, color-mix(in srgb, var(--cyan) 12%, transparent) 100%),
              var(--surface_alpha);
  box-shadow: 0 20px 44px -26px color-mix(in srgb, var(--secondary) 75%, transparent); }
.kp-page-head::before { content:""; position:absolute; left:0; top:0; bottom:0; width:5px;
  background: linear-gradient(180deg, var(--primary), var(--fuchsia), var(--secondary), var(--cyan)); }
.kp-page-head::after { content:""; position:absolute; right:-70px; top:-90px; width:260px; height:260px; border-radius:50%;
  background: radial-gradient(circle, color-mix(in srgb, var(--fuchsia) 30%, transparent), transparent 65%); pointer-events:none; }
.kp-page-title { font-size: 1.75rem; font-weight: 850; margin: 0; line-height: 1.25;
  background: linear-gradient(90deg, var(--title1), var(--title2) 55%, var(--title3));
  -webkit-background-clip: text; -webkit-text-fill-color: transparent; }
.kp-page-sub { color: var(--muted); margin: .3rem 0 0; font-size: .94rem; }

/* metric cards */
.kp-grid { display:grid; grid-template-columns: repeat(auto-fit, minmax(170px, 1fr)); gap: .85rem; margin: .4rem 0 1rem; }
.kp-card { border: 1px solid var(--border); border-radius: 16px; padding: 1rem 1.1rem; position: relative; overflow: hidden;
  background: linear-gradient(150deg, color-mix(in srgb, var(--accent, var(--primary)) 24%, transparent) 0%, transparent 65%), var(--surface);
  box-shadow: 0 10px 28px -20px color-mix(in srgb, var(--accent, var(--primary)) 80%, transparent);
  transition: transform .18s ease, border-color .18s ease, box-shadow .18s ease; }
.kp-card:hover { transform: translateY(-3px); border-color: color-mix(in srgb, var(--accent, var(--primary)) 60%, transparent);
  box-shadow: 0 18px 38px -16px color-mix(in srgb, var(--accent, var(--primary)) 75%, transparent); }
.kp-card::before { content:""; position:absolute; inset:0 auto 0 0; width:4px;
  background: linear-gradient(180deg, var(--accent, var(--primary)), color-mix(in srgb, var(--accent, var(--primary)) 30%, transparent)); }
.kp-card::after { content:""; position:absolute; right:-30px; top:-30px; width:90px; height:90px; border-radius:50%;
  background: radial-gradient(circle, color-mix(in srgb, var(--accent, var(--primary)) 28%, transparent), transparent 70%); }
.kp-card .lbl { color: color-mix(in srgb, var(--accent, var(--primary)) 70%, var(--muted)); font-size: .76rem;
  text-transform: uppercase; letter-spacing: .08em; font-weight: 750; }
.kp-card .val { font-size: 1.85rem; font-weight: 850; margin-top: .2rem; line-height: 1.1; color: var(--text); }
.kp-card .sub { color: var(--muted); font-size: .8rem; margin-top: .25rem; }

/* pills / badges */
.kp-pill { display:inline-flex; align-items:center; gap:.35rem; padding: .2rem .62rem; border-radius: 999px;
  font-size: .76rem; font-weight: 650; border: 1px solid transparent; white-space: nowrap; margin: 0 .25rem .25rem 0;
  --c: var(--muted); color: var(--c); background: color-mix(in srgb, var(--c) 13%, transparent);
  border-color: color-mix(in srgb, var(--c) 34%, transparent); }
.kp-pill.ok { --c: var(--success); } .kp-pill.warn { --c: var(--warning); } .kp-pill.bad { --c: var(--danger); }
.kp-pill.info { --c: var(--secondary); } .kp-pill.pri { --c: var(--primary); } .kp-pill.cyan { --c: var(--cyan); }

/* banners */
.kp-banner { border-radius: 14px; padding: .85rem 1.05rem; margin: .4rem 0 1rem; font-size: .9rem; color: var(--text);
  --c: var(--warning); border: 1px solid color-mix(in srgb, var(--c) 40%, transparent);
  background: linear-gradient(100deg, color-mix(in srgb, var(--c) 16%, transparent), color-mix(in srgb, var(--c) 5%, transparent)); }
.kp-banner.info { --c: var(--secondary); }
.kp-banner b { color: color-mix(in srgb, var(--c) 75%, var(--text)); }

/* promo blocks */
.kp-seg { display:inline-block; font-family: 'JetBrains Mono', ui-monospace, monospace; font-size: .82rem; color: var(--text);
  background: linear-gradient(135deg, color-mix(in srgb, var(--cyan) 12%, var(--surface2)), var(--surface2));
  border: 1px solid color-mix(in srgb, var(--cyan) 30%, transparent); padding: .25rem .6rem; border-radius: 9px; margin: 0 .3rem .3rem 0; }
.kp-arrow { color: var(--primary); font-weight: 800; margin: 0 .25rem; }
.kp-quote { border-left: 4px solid var(--q, var(--primary)); padding: .65rem .85rem; border-radius: 0 12px 12px 0; margin: .2rem 0 .6rem;
  background: linear-gradient(90deg, color-mix(in srgb, var(--q, var(--primary)) 14%, var(--surface2)), var(--surface2)); }
.kp-quote .k { font-size: .72rem; text-transform: uppercase; letter-spacing: .08em; font-weight: 800;
  color: color-mix(in srgb, var(--q, var(--primary)) 75%, var(--muted)); }
.kp-quote .t { font-size: .96rem; margin-top: .15rem; color: var(--text); }
.kp-bar { display:flex; align-items:center; gap:.6rem; margin: .2rem 0; font-size: .82rem; }
.kp-bar .n { width: 132px; color: var(--muted); }
.kp-bar .track { flex:1; height: 8px; background: color-mix(in srgb, var(--muted) 18%, transparent); border-radius: 99px; overflow:hidden; }
.kp-bar .fill { height:100%; border-radius: 99px; background: linear-gradient(90deg, var(--cyan), var(--secondary), var(--primary)); }
.kp-bar .v { width: 38px; text-align:right; font-weight: 700; color: var(--text); }
.kp-muted { color: var(--muted); font-size: .86rem; }
.kp-stepper { display:flex; gap:.5rem; flex-wrap:wrap; margin: .3rem 0 1rem; }
.kp-step { flex:1; min-width: 120px; padding: .6rem .75rem; border-radius: 13px; background: var(--surface);
  border: 1px solid var(--border); font-size: .8rem; color: var(--text); }
.kp-step.done { border-color: color-mix(in srgb, var(--success) 50%, transparent);
  background: linear-gradient(160deg, color-mix(in srgb, var(--success) 20%, transparent), transparent 72%), var(--surface); }
.kp-step.done b::before { content: "✓ "; color: var(--success); }
.kp-step.run { border-color: color-mix(in srgb, var(--warning) 60%, transparent);
  box-shadow: 0 0 0 3px color-mix(in srgb, var(--warning) 15%, transparent); }
.kp-step .s { color: var(--muted); font-size: .72rem; }

/* streamlit widgets */
div[data-testid="stExpander"] { background: var(--surface); border: 1px solid var(--border); border-radius: 16px;
  box-shadow: 0 10px 30px -24px color-mix(in srgb, var(--secondary) 80%, transparent); }
div[data-testid="stExpander"] details summary { padding: .8rem .95rem; }
div[data-testid="stExpander"] details summary p { font-weight: 700; font-size: .98rem; }
div[data-testid="stExpander"]:hover { border-color: color-mix(in srgb, var(--secondary) 45%, transparent); }
div[data-testid="stVerticalBlockBorderWrapper"] { border-color: var(--border) !important; }
.stTabs [data-baseweb="tab-list"] { gap: .45rem; }
.stTabs [data-baseweb="tab"] { background: var(--surface); border: 1px solid var(--border); border-radius: 12px 12px 0 0; padding: .5rem 1.05rem; }
.stTabs [aria-selected="true"] { background: linear-gradient(180deg, color-mix(in srgb, var(--primary) 24%, transparent), var(--surface));
  border-color: color-mix(in srgb, var(--primary) 45%, transparent); }
.stButton > button, .stDownloadButton > button { border-radius: 11px; font-weight: 650; border: 1px solid var(--border); }
.stButton > button[kind="primary"], .stDownloadButton > button[kind="primary"] { color: #fff; border: none;
  background: linear-gradient(95deg, var(--primary), var(--fuchsia) 55%, var(--secondary));
  box-shadow: 0 10px 26px -10px color-mix(in srgb, var(--primary) 80%, transparent); }
.stButton > button[kind="primary"]:hover, .stDownloadButton > button[kind="primary"]:hover { filter: brightness(1.08) saturate(1.1); }
div[data-testid="stDataFrame"], div[data-testid="stDataEditor"] { border-radius: 14px; overflow: hidden; }
.stButton > button:disabled, .stDownloadButton > button:disabled { opacity: .45; filter: grayscale(.6); box-shadow: none; cursor: not-allowed; }
/* the Find Promos buttons stay colourful while a run is going ("Running…"); other disabled buttons fade */
.st-key-find_promos button:disabled, .st-key-find_promos_upload button:disabled {
  opacity: .78; filter: none; color: #fff !important; cursor: progress;
  background: linear-gradient(95deg, var(--primary), var(--secondary)) !important;
  animation: kp-pulse 1.6s ease-in-out infinite; }
@keyframes kp-pulse { 0%, 100% { opacity: .7; } 50% { opacity: .95; } }
/* the main call-to-action */
.st-key-find_promos button { font-size: 1.02rem; font-weight: 750; padding: .7rem 1rem; letter-spacing: .01em; }

/* Streamlit's built-in presets use a red accent. Re-tint accent widgets to this palette. */
div[data-testid="stSlider"] [data-baseweb="slider"],
label[data-baseweb="radio"] > div:first-child,
label[data-baseweb="checkbox"] > div:first-child,
div[data-testid="stProgress"] { filter: hue-rotate(var(--accent-hue)) saturate(var(--accent-sat)); }
[data-baseweb="tab-highlight"] { background-color: var(--primary) !important; }
span[data-baseweb="tag"] { background: linear-gradient(95deg, var(--primary), var(--secondary)) !important;
  color: #fff !important; border-radius: 8px !important; }
div[data-baseweb="input"], div[data-baseweb="select"] > div, div[data-baseweb="textarea"], div[data-baseweb="base-input"] {
  background-color: var(--surface2) !important; border-color: var(--border) !important; }
div[data-baseweb="input"]:focus-within, div[data-baseweb="select"] > div:focus-within, div[data-baseweb="textarea"]:focus-within {
  border-color: var(--primary) !important; box-shadow: 0 0 0 3px color-mix(in srgb, var(--primary) 18%, transparent) !important; }
div[data-baseweb="popover"] ul { background: var(--surface) !important; }
code { color: var(--primary); background: color-mix(in srgb, var(--primary) 9%, transparent); }
@media (max-width: 640px) { .kp-hero h1 { font-size: 1.7rem; } .kp-bar .n { width: 96px; } }
</style>
"""


# Light mode: flatten the dark-mode effects (no glows, no animated or gradient text, quiet cards).
LIGHT_CSS = """
<style>
.stApp { background: var(--bg) !important; }
header[data-testid="stHeader"]::after { height: 2px; animation: none; background: var(--primary); opacity: .85; }
section[data-testid="stSidebar"] [data-testid="stSidebarNav"] a[aria-current="page"] {
  background: color-mix(in srgb, var(--primary) 9%, transparent); box-shadow: inset 3px 0 0 var(--primary); }
section[data-testid="stSidebar"] [data-testid="stSidebarNav"] a:hover { background: #F3F4F6; }
.kp-brand span { background: none; -webkit-text-fill-color: var(--primary); }
h4 { background: none; -webkit-text-fill-color: var(--text); }
.kp-hero { background: var(--surface); box-shadow: 0 1px 3px rgba(17,24,39,.06); border-color: var(--border); }
.kp-hero h1 { background: none; animation: none; filter: none; -webkit-text-fill-color: var(--text); }
.kp-hero h1::first-letter { color: var(--primary); }
.kp-page-head { background: var(--surface); box-shadow: 0 1px 3px rgba(17,24,39,.05); border-color: var(--border); }
.kp-page-head::before { width: 4px; background: var(--primary); }
.kp-page-head::after { display: none; }
.kp-page-title { background: none; -webkit-text-fill-color: var(--text); }
.kp-card { background: var(--surface); box-shadow: 0 1px 2px rgba(17,24,39,.05); }
.kp-card:hover { transform: translateY(-1px); border-color: color-mix(in srgb, var(--accent, var(--primary)) 35%, var(--border));
  box-shadow: 0 4px 12px -4px rgba(17,24,39,.10); }
.kp-card::before { width: 3px; background: var(--accent, var(--primary)); }
.kp-card::after { display: none; }
.kp-card .lbl { color: var(--muted); }
.kp-pill { background: color-mix(in srgb, var(--c) 8%, #fff); border-color: color-mix(in srgb, var(--c) 22%, #fff); }
.kp-banner { background: color-mix(in srgb, var(--c) 7%, #fff); border-color: color-mix(in srgb, var(--c) 25%, #fff); }
.kp-seg { background: var(--surface2); border-color: var(--border); }
.kp-quote { background: var(--surface2); }
.kp-bar .fill { background: var(--primary); }
.kp-step.done { background: var(--surface); border-color: color-mix(in srgb, var(--success) 35%, var(--border)); }
div[data-testid="stExpander"] { box-shadow: 0 1px 2px rgba(17,24,39,.04); }
div[data-testid="stExpander"]:hover { border-color: color-mix(in srgb, var(--primary) 30%, var(--border)); }
.stTabs [aria-selected="true"] { background: var(--surface); border-color: var(--border);
  box-shadow: inset 0 -2px 0 var(--primary); }
.stButton > button[kind="primary"], .stDownloadButton > button[kind="primary"] {
  background: linear-gradient(95deg, #4F46E5, #7C3AED); box-shadow: 0 6px 16px -6px rgba(79,70,229,.55); }
.stButton > button[kind="primary"]:hover, .stDownloadButton > button[kind="primary"]:hover { filter: brightness(1.06); }
</style>
"""


def current_mode() -> str:
    """Follow the active Streamlit theme (sidebar toggle or the ⋮ menu)."""
    try:
        t = st.context.theme.type
        if t in PALETTES:
            return t
    except Exception:
        pass
    return st.session_state.get("kp_mode", "dark")


def inject() -> str:
    mode = current_mode()
    C.clear()
    C.update(PALETTES[mode])
    root = ":root, .stApp {" + "".join(f"--{k}:{v};" for k, v in C.items()) + "}"
    st.markdown(f"<style>{root}</style>" + CSS + (LIGHT_CSS if mode == "light" else ""), unsafe_allow_html=True)
    return mode


def esc(x) -> str:
    return html.escape(str(x if x is not None else ""))


def pill(text: str, kind: str = "mute") -> str:
    return f'<span class="kp-pill {kind}">{esc(text)}</span>'


def page_header(title: str, subtitle: str = "") -> None:
    st.markdown(f'<div class="kp-page-head"><div class="kp-page-title">{esc(title)}</div>'
                + (f'<div class="kp-page-sub">{esc(subtitle)}</div>' if subtitle else "") + "</div>",
                unsafe_allow_html=True)


def banner(html_text: str, kind: str = "") -> None:
    st.markdown(f'<div class="kp-banner {kind}">{html_text}</div>', unsafe_allow_html=True)
