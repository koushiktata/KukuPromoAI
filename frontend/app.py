"""KukuPromo AI - Streamlit frontend. Run from the project root:  streamlit run frontend/app.py

Locally you normally run the FastAPI backend yourself (uvicorn backend.main:app --port 8000).
If no backend is reachable (e.g. on Streamlit Community Cloud), the app starts the same FastAPI
backend inside this process, and API keys can then only come from the host's secrets."""
import os
import socket
import sys
import threading
import time
from pathlib import Path

FRONTEND = Path(__file__).resolve().parent
sys.path.insert(0, str(FRONTEND))

import requests  # noqa: E402
import streamlit as st  # noqa: E402

st.set_page_config(page_title="KukuPromo AI", page_icon="🎬", layout="wide", initial_sidebar_state="expanded")


def _reachable(url: str) -> bool:
    try:
        return requests.get(f"{url}/api/health", timeout=1.5).ok
    except requests.RequestException:
        return False


@st.cache_resource(show_spinner="Starting the KukuPromo AI engine…")
def _embedded_backend() -> str:
    """Run the FastAPI backend in a background thread of this process (once per server)."""
    import uvicorn
    sys.path.insert(0, str(FRONTEND.parent))
    os.chdir(FRONTEND.parent)
    os.environ["KUKU_LOCK_KEYS"] = "1"          # hosted: keys come from the host's secrets only
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    from backend.main import app as fastapi_app
    server = uvicorn.Server(uvicorn.Config(fastapi_app, host="127.0.0.1", port=port, log_level="warning"))
    server.install_signal_handlers = lambda: None   # not the main thread
    threading.Thread(target=server.run, daemon=True, name="kukupromo-backend").start()
    url = f"http://127.0.0.1:{port}"
    for _ in range(100):
        if _reachable(url):
            break
        time.sleep(0.2)
    return url


if not os.getenv("BACKEND_URL") and (os.getenv("KUKU_EMBED_BACKEND") or not _reachable("http://localhost:8000")):
    os.environ["BACKEND_URL"] = _embedded_backend()

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
