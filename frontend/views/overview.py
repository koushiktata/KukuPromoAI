import streamlit as st

import api_client as api
from components.cards import compact_promo_card, metric_cards, review_metrics, timestamp_table
from components.charts import promos_per_episode, score_histogram
from components.theme import C, esc, pill
from views.common import api_error_box, follow_run, posting_warning, promos, run_status_pill, start_run, summary


def _judges_label(opts: dict) -> str:
    provs = opts.get("providers") or [opts.get("provider", "mock")]
    if provs == ["mock"]:
        return "Mock (offline rules)"
    return ("Judge panel: " if len(provs) > 1 else "") + " + ".join(p.capitalize() for p in provs)


def render():
    s = summary()
    run = (s or {}).get("run")
    show_pill = pill("📺 " + s["show_name"], "info") if s and s.get("show_name") else ""
    judges = s.get("judges") if s else []
    judge_pill = pill("⚖️ " + " + ".join(judges), "cyan") if judges else ""
    st.markdown(f"""<div class="kp-hero"><div><h1>KukuPromo AI</h1>
      <p>Upload a show's screenplays → get the exact timestamps to cut 20–60s promos</p></div>
      <div>{run_status_pill(run)}{show_pill}{judge_pill}</div></div>""", unsafe_allow_html=True)
    api_error_box()
    health = api.safe_get("/api/health") or {}
    running = bool(health.get("running_run")) or bool(st.session_state.get("active_run"))
    opts = dict(st.session_state.get("run_options") or {})
    opts.pop("episodes_txt", None)
    shows = api.safe_get("/api/shows", {}, {"shows": []})["shows"]

    up, ex = st.columns([1.25, 1])
    with up:
        with st.container(border=True):
            st.markdown("##### 📤 Upload a show")
            name = st.text_input("Show name", placeholder="e.g. The Billionaire's Secret Bride", key="up_name")
            files = st.file_uploader("Episode screenplays (.txt) — select all episodes at once", type="txt",
                                     accept_multiple_files=True, key=f"up_files_{st.session_state.get('up_n', 0)}")
            st.caption(f"{len(files or [])} file(s) selected · each file = one timestamped episode")
            if st.button("⏳  Running…" if running else "🚀  Upload & find promos", type="primary",
                         use_container_width=True, disabled=running, key="find_promos_upload"):
                if not files:
                    st.warning("Select the episode files first.")
                else:
                    try:
                        r = api.upload_show(name or "Uploaded show", files)
                        msg = f"Saved {len(r['saved'])} episode(s) as “{r['show']['name']}”."
                        if r["rejected"]:
                            msg += f" Skipped {len(r['rejected'])}: " + "; ".join(
                                f"{x['file']} ({x['reason']})" for x in r["rejected"][:3])
                        st.toast(msg, icon="📤")
                        st.session_state["run_show"] = r["show"]["show_id"]          # select the new show
                        st.session_state["up_n"] = st.session_state.get("up_n", 0) + 1   # clear the file box
                        start_run({**opts, "show": r["show"]["show_id"]})
                        st.rerun()
                    except api.APIError as e:
                        st.error(str(e))
    with ex:
        with st.container(border=True):
            st.markdown("##### 🎬 Or run on a saved show")
            ids = [x["show_id"] for x in shows] or ["default"]
            cur = s.get("show_id") if s and s.get("show_id") in ids else ids[0]
            show_id = st.selectbox("Show", ids, index=ids.index(cur), key="run_show",
                                   format_func=lambda i: next((f"{x['name']} · {x['files']} episodes" for x in shows
                                                               if x["show_id"] == i), i))
            st.markdown(f"<div class='kp-muted' style='margin:.2rem 0 .6rem'>Judges: <b>{esc(_judges_label(opts))}</b> "
                        f"· change in Settings</div>", unsafe_allow_html=True)
            if st.button("⏳  Running…" if running else "🎬  Find Promos", type="primary", use_container_width=True,
                         disabled=running, key="find_promos"):
                start_run({**opts, "show": show_id})
                st.rerun()
    follow_run()
    if run and run["status"] == "FAILED":
        last = (run.get("errors") or [{}])[-1]
        err = last.get("error", "")
        setup_failure = last.get("task_id") == "setup"
        if setup_failure:
            st.warning(f"The last run didn't start: {err}. Add the key to `.env` and restart the backend, or switch "
                       "the provider to **Mock** in Settings. The results below are from the last successful run.")
        else:
            st.error(f"Last run failed: {err}")
        if not setup_failure and st.button("↻ Resume from checkpoint"):
            try:
                api.post(f"/api/process/resume/{run['run_id']}")
                st.session_state["active_run"] = run["run_id"]
                st.rerun()
            except api.APIError as e:
                st.error(str(e))
    if not s or not s["ranked"]:
        st.info("No results yet. Upload a show's screenplays (or pick a saved show) and press **Find Promos**.")
        return

    results(s, run)


def _status_box(run: dict | None, s: dict) -> None:
    """'✓ Done' box like the reference (or Running / Failed)."""
    status = (run or {}).get("status", "")
    label = {"COMPLETED": "Done", "RUNNING": "Running…", "FAILED": "Last run failed — showing the last good results"}.get(
        status, "Done")
    state = {"COMPLETED": "complete", "RUNNING": "running", "FAILED": "error"}.get(status, "complete")
    title = f"{label}  ·  {s.get('show_name') or 'show'}  ·  judges: {' + '.join(s.get('judges') or ['mock'])}"
    with st.status(title, state=state, expanded=False):
        m = (run or {}).get("metrics", {})
        st.write(f"Run `{(run or {}).get('run_id', '-')}` · {m.get('task_counts', {}).get('COMPLETED', '?')} agent tasks "
                 f"completed · {m.get('candidates', s['candidates'])} candidates checked against the screenplay timestamps.")


def _downloads(s: dict) -> None:
    n_appr = s["review"]["approved"]
    c1, c2, c3 = st.columns(3)
    appr, _ = api.download("/api/reports/approved", (("fmt", "csv"),))
    allc, _ = api.download("/api/reports/all-decisions")
    full, _ = api.download("/api/reports/full")
    c1.download_button(f"⬇ Approved promos only ({n_appr})", appr, "approved_promos.csv", use_container_width=True,
                       disabled=n_appr == 0, help="Approve promos below first" if n_appr == 0 else None)
    c2.download_button("⬇ All promos + decisions (CSV)", allc, "all_promos_decisions.csv", use_container_width=True)
    c3.download_button("⬇ Full report (ranked.md)", full, "ranked.md", use_container_width=True)


def results(s: dict, run: dict | None) -> None:
    """Results right under the upload box: status → metrics → review + downloads → warning → secrets → tabs."""
    _status_box(run, s)
    secs = s["processing_seconds"]
    metric_cards([
        ("Episodes", str(s["episodes"]), "screenplays parsed", C["secondary"]),
        ("Candidates", f"{s['candidates']:,}", "20–60s cuts generated", C["cyan"]),
        ("Passed the rules", f"{s['passed_rules']:,}", "fully valid before ranking", C["success"]),
        ("Ranked promos", str(s["ranked"]), f"{s['new_viewer']} new-viewer · {s['retarget']} re-targeting", C["primary"]),
        ("Time", f"{secs / 60:.1f} min" if secs is not None else "—", f"{secs:.1f}s" if secs is not None else "",
         C["warning"]),
    ])
    st.markdown("#### Editor review")
    review_metrics(s["review"])
    _downloads(s)
    posting_warning(s)

    secrets = api.safe_get("/api/secrets", {}, {"secrets": [], "disclaimer": ""})
    with st.expander("🔒 The show's secrets (what the tool treats as spoilers): check once"):
        st.caption(secrets.get("disclaimer", ""))
        for x in secrets["secrets"]:
            k = {"verified": "ok", "incorrect": "bad", "needs_review": "warn"}.get(x["review"]["status"], "mute")
            st.markdown(f"{pill(x['severity'], 'bad' if x['severity'] == 'high' else 'warn')}{pill(x['review']['status'], k)} "
                        f"**Ep {x['reveal_episode']}** · {esc(x['description'])}", unsafe_allow_html=True)
        st.caption("Verify each one on the Spoilers & Secrets page.")

    allp = promos()
    counts = allp["category_counts"]
    t1, t2 = st.tabs([f"For new viewers ({counts['new_viewer']})", f"Re-targeting / spoilers ({counts['retarget']})"])
    for tab, cat in ((t1, "new_viewer"), (t2, "retarget")):
        with tab:
            items = promos(category=cat)["promos"]
            if not items:
                st.info("No promos in this group for this show.")
            for i, p in enumerate(items[:10]):
                compact_promo_card(p, expanded=(i == 0), key_prefix=f"ov{cat}")
            if len(items) > 10:
                st.caption(f"Showing the top 10 of {len(items)} — see all in Promo Discovery.")

    data = allp["promos"]
    with st.expander("⏱ All promo timestamps (table)"):
        timestamp_table(data)
    if data:
        with st.expander("📊 Charts"):
            c1, c2 = st.columns(2)
            with c1:
                st.plotly_chart(promos_per_episode(data, s["episodes"]), use_container_width=True,
                                config={"displayModeBar": False})
            with c2:
                st.plotly_chart(score_histogram(data), use_container_width=True, config={"displayModeBar": False})
