"""KukuPromo AI - Streamlit frontend. Run from the project root:  streamlit run frontend/app.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import streamlit as st  # noqa: E402

st.set_page_config(page_title="KukuPromo AI", page_icon="🎬", layout="wide", initial_sidebar_state="expanded")

import api_client as api  # noqa: E402
from components.theme import inject, pill  # noqa: E402
from views import discovery, exports, overview, review, safety, secrets, settings, trace  # noqa: E402

MODE = inject()

pages = [
    st.Page(overview.render, title="Overview Dashboard", icon=":material/space_dashboard:", url_path="overview", default=True),
    st.Page(discovery.render, title="Promo Discovery", icon=":material/movie_filter:", url_path="discovery"),
    st.Page(review.render, title="Editor Review", icon=":material/fact_check:", url_path="review"),
    st.Page(secrets.render, title="Spoilers & Secrets", icon=":material/lock:", url_path="secrets"),
    st.Page(safety.render, title="Content Safety", icon=":material/health_and_safety:", url_path="safety"),
    st.Page(trace.render, title="Agent Execution Trace", icon=":material/account_tree:", url_path="trace"),
    st.Page(exports.render, title="Reports & Exports", icon=":material/download:", url_path="exports"),
    st.Page(settings.render, title="Settings", icon=":material/tune:", url_path="settings"),
]

with st.sidebar:
    st.markdown("<div class='kp-brand'>🎬 KukuPromo <span>AI</span></div>"
                "<div class='kp-brand-sub'>Promo discovery for microdramas</div>", unsafe_allow_html=True)

nav = st.navigation(pages)


def _switch_theme() -> None:
    st.session_state["kp_switch_to"] = "dark" if st.session_state["kp_dark"] else "light"


with st.sidebar:
    st.toggle("🌙 Dark mode" if MODE == "dark" else "☀️ Light mode", value=(MODE == "dark"), key="kp_dark",
              on_change=_switch_theme, help="Switch between the dark and light theme")
    target = st.session_state.pop("kp_switch_to", None)
    if target:
        # Streamlit remembers the theme per page path in localStorage; set it for every page, then reload.
        paths = ["/"] + [f"/{p.url_path}" for p in pages]
        name = "Dark" if target == "dark" else "Light"
        st.components.v1.html(
            "<script>const ls = window.parent.localStorage;"
            f"for (const p of {paths!r}) ls.setItem('stActiveTheme-' + p + '-v1', JSON.stringify({{name: '{name}'}}));"
            "window.parent.location.reload();</script>", height=0)

with st.sidebar:
    st.divider()
    h = api.safe_get("/api/health")
    if h:
        st.markdown(pill("● backend online", "ok") + (pill("run in progress", "warn") if h.get("running_run") else ""),
                    unsafe_allow_html=True)
        st.caption(f"{h['data_files']} screenplays · {h['provider']}")
    else:
        st.markdown(pill("● backend offline", "bad"), unsafe_allow_html=True)
        st.caption("Start it: `uvicorn backend.main:app --port 8000`")
        st.session_state.pop("_api_error", None)
    st.caption("📤 Upload a new show's screenplays on the Overview page.")

nav.run()
