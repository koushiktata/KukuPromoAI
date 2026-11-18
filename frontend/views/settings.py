import streamlit as st

import api_client as api
from components.theme import banner, esc, page_header, pill
from views.common import api_error_box, follow_run, start_run

PROVIDERS = {"mock": "Mock / heuristic (offline, free)", "groq": "Groq", "gemini": "Google Gemini",
             "openrouter": "OpenRouter", "openai": "OpenAI", "ollama": "Ollama (local)"}
DEFAULT_MODELS = {"groq": "openai/gpt-oss-120b", "gemini": "gemini-3.5-flash",
                  "openrouter": "meta-llama/llama-3.3-70b-instruct:free", "openai": "gpt-4o-mini", "ollama": "llama3.1",
                  "mock": ""}
W = [("hook", "Hook strength", 25), ("cliffhanger", "Cliffhanger strength", 30), ("standalone", "Standalone context", 20),
     ("emotion", "Emotional intensity", 15), ("coherence", "Narrative coherence", 10)]


def key_panel(p: dict, model: str = "", prefix: str = "") -> None:
    """Add / test / remove the API key for one provider. The key is write-only."""
    prov = p["provider"]
    name = PROVIDERS.get(prov, prov)
    if prov == "ollama":
        st.markdown(f"{pill('no key needed', 'ok')} Ollama runs locally at <code>localhost:11434</code>.",
                    unsafe_allow_html=True)
        return
    if st.session_state.get("_keys_locked"):
        # hosted deployment: keys come from the host's secrets; visitors can't see, add or remove them
        st.markdown(pill("✓ available on this app" if p["set"] else "not set up on this app",
                         "ok" if p["set"] else "mute"), unsafe_allow_html=True)
        return
    if p["set"]:
        st.markdown(f"{pill('✓ key saved ' + p['hint'], 'ok')} {pill(p['env_var'], 'mute')}", unsafe_allow_html=True)
    else:
        st.markdown(f"{pill('no key yet', 'warn')} Get a free key: [{esc(p['get_key_url'])}]({p['get_key_url']})",
                    unsafe_allow_html=True)
    c1, c2, c3, c4 = st.columns([3, 1, 1, 1])
    key = c1.text_input(f"{name} API key", type="password", key=f"{prefix}key_{prov}",
                        placeholder="paste to replace the saved key" if p["set"] else "paste your API key",
                        label_visibility="collapsed")
    if c2.button("Save key", key=f"{prefix}save_{prov}", type="primary", use_container_width=True):
        if not key.strip():
            st.warning("Paste the key into the box first.")
            return
        try:
            api.put(f"/api/settings/keys/{prov}", {"api_key": key.strip()})
            st.session_state.pop(f"{prefix}key_{prov}", None)
            st.toast(f"{name} key saved", icon="🔑")
            st.rerun()
        except api.APIError as e:
            st.error(str(e))
    if c3.button("Test", key=f"{prefix}test_{prov}", use_container_width=True, disabled=not p["set"]):
        with st.spinner(f"Calling {name}…"):
            try:
                r = api.post(f"/api/settings/keys/{prov}/test", {"model": model or None}, timeout=120)
                if r["ok"]:
                    st.success(f"{name} works ✓ (model {r['model']})")
                else:
                    st.error(f"{name} test failed: {r['error']}")
            except api.APIError as e:
                st.error(str(e))
    if c4.button("Remove", key=f"{prefix}del_{prov}", use_container_width=True, disabled=not p["set"]):
        try:
            api.delete(f"/api/settings/keys/{prov}")
            st.toast(f"{name} key removed", icon="🗑️")
            st.rerun()
        except api.APIError as e:
            st.error(str(e))


def render():
    page_header("Settings", "Model, API keys, scoring weights and processing options for the next run.")
    api_error_box()
    h = api.safe_get("/api/health")
    if h:
        st.markdown(f"Backend {pill('online', 'ok')} {pill(api.BACKEND, 'mute')} {pill(str(h['data_files']) + ' screenplay files', 'info')}"
                    f" {pill('server default: ' + h['provider'], 'mute')}", unsafe_allow_html=True)
    kd = api.safe_get("/api/settings/keys", {}, {"providers": [], "locked": False})
    st.session_state["_keys_locked"] = bool(kd.get("locked"))
    keys = {p["provider"]: p for p in kd["providers"]}
    if kd.get("locked"):
        banner("🔒 On this hosted app, API keys are managed by the app owner (host secrets). Offline (mock) "
               "always works; LLM judges are available only where the owner has set a key.", "info")
    opts = st.session_state.get("run_options") or {}
    saved_provs = opts.get("providers") or ([opts["provider"]] if opts.get("provider") else ["mock"])
    st.markdown("#### Judges")
    if "judge_mode" not in st.session_state:
        st.session_state["judge_mode"] = "Offline (mock)" if saved_provs == ["mock"] else "LLM judges"
    mode = st.radio("Who scores the candidate promos?", ["Offline (mock)", "LLM judges"], horizontal=True,
                    key="judge_mode", help="Mock = rule engine only, free and instant. LLM judges = one or more "
                                           "real models score every episode's best candidates.")
    models: dict[str, str] = {}
    if mode == "Offline (mock)":
        provs = ["mock"]
        st.caption("Rules only: no network, no keys, ~5 seconds for 50 episodes.")
    else:
        real = [p for p in PROVIDERS if p != "mock"]
        if "judge_select" not in st.session_state:
            st.session_state["judge_select"] = [p for p in saved_provs if p in real] or ["groq"]
        provs = st.multiselect("Pick one or more LLMs (several = a judge panel: scores are averaged, "
                               "disagreement is flagged for review)", real, format_func=PROVIDERS.get, key="judge_select")
        if len(provs) > 1:
            banner(f"⚖️ <b>Judge panel of {len(provs)}</b>: each model scores the same candidates in parallel; "
                   "the average is used, and promos where they disagree are sent to a human.", "info")
        for prov in provs:
            with st.container(border=True):
                c1, c2 = st.columns([1, 1.4])
                c1.markdown(f"**{esc(PROVIDERS[prov])}**")
                models[prov] = c2.text_input(f"{PROVIDERS[prov]} model", (opts.get("models") or {}).get(prov)
                                             or DEFAULT_MODELS[prov], key=f"model_{prov}", label_visibility="collapsed")
                if prov in keys:
                    key_panel(keys[prov], models[prov])
    st.caption("🔒 Keys are write-only: saved to the backend's git-ignored .env and never shown again (only the "
               "last 4 characters). LLMs only score and explain candidates that code generated; they never set timestamps.")
    with st.expander("🔑 Manage all API keys" if not kd.get("locked") else "🔑 LLMs available on this app"):
        for p in keys.values():
            st.markdown(f"**{esc(PROVIDERS.get(p['provider'], p['provider']))}** "
                        f"<span class='kp-muted'>· default model {esc(p['default_model'])}</span>", unsafe_allow_html=True)
            key_panel(p, prefix="all_")
            st.divider()
    st.markdown("#### Scoring weights")
    st.caption("Our own assumption, not official Kuku criteria. Normalised to 100%.")
    cols = st.columns(5)
    w = {k: cols[i].slider(lbl, 0, 60, int((opts.get("weights") or {}).get(k, d / 100) * 100)) for i, (k, lbl, d) in enumerate(W)}
    tot = sum(w.values()) or 1
    st.markdown(" ".join(pill(f"{k} {v / tot * 100:.0f}%", "info") for k, v in w.items()), unsafe_allow_html=True)
    st.markdown("#### Processing")
    c1, c2 = st.columns(2)
    retries = c1.number_input("Max retries per task", 0, 5, int(opts.get("max_retries", 2)))
    eps_txt = c2.text_input("Episodes (blank = all, e.g. 1-10 or 1,5,9)", opts.get("episodes_txt", ""))
    eps = None
    if eps_txt.strip():
        try:
            eps = []
            for part in eps_txt.split(","):
                a, _, b = part.strip().partition("-")
                eps += list(range(int(a), int(b or a) + 1))
        except ValueError:
            st.error("Episodes must look like 1-10 or 1,5,9")
            eps = None
    new = {"providers": provs or ["mock"], "max_retries": int(retries),
           "weights": {k: v / tot for k, v in w.items()}, "episodes_txt": eps_txt}
    if models:
        new["models"] = models
    if eps:
        new["episodes"] = eps
    missing = [p for p in provs if p not in ("mock", "ollama") and not keys.get(p, {}).get("set", False)]
    blocked = bool(missing) or not provs
    if not provs:
        st.warning("Pick at least one LLM, or switch to Offline (mock).")
    elif missing:
        st.warning("Add the API key for " + ", ".join(PROVIDERS[p] for p in missing) +
                   " above (or remove it from the panel) to run.")
    c1, c2 = st.columns([1, 1])
    if c1.button("💾 Save settings", use_container_width=True, disabled=blocked):
        st.session_state["run_options"] = new
        st.toast("Saved: the next Find Promos uses these judges", icon="💾")
    if c2.button("🎬 Save & run now", type="primary", use_container_width=True, disabled=blocked):
        st.session_state["run_options"] = new
        run_opts = {k: v for k, v in new.items() if k != "episodes_txt"}
        run_opts["show"] = st.session_state.get("run_show", "default")
        start_run(run_opts)
    follow_run()
