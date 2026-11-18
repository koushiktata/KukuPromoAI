"""Data loading + shared widgets used by several pages."""
from __future__ import annotations

import time

import streamlit as st

import api_client as api
from components.theme import banner, esc, pill

WARNING = ("<b>Before posting:</b> review potential graphic/sexual content flags and check the show's secrets list. "
           "Spoiler labels are AI-generated and must be verified.")


def summary() -> dict | None:
    return api.safe_get("/api/reports/summary")


def promos(**filters) -> dict:
    return api.safe_get("/api/promos", {k: v for k, v in filters.items() if v is not None},
                        {"count": 0, "promos": [], "category_counts": {"new_viewer": 0, "retarget": 0}})


def lookups() -> tuple[dict, dict]:
    flags = api.safe_get("/api/content-flags", {}, {"flags": []})["flags"]
    secrets = api.safe_get("/api/secrets", {}, {"secrets": []})["secrets"]
    return {f["flag_id"]: f for f in flags}, {s["secret_id"]: s for s in secrets}


def posting_warning(s: dict | None) -> None:
    if not s:
        return
    if s["posting_warning"]:
        bits = []
        if s["flags_unreviewed"]:
            bits.append(f"{s['flags_unreviewed']} content flags in ranked promos are unreviewed"
                        + (f" ({s['high_severity_flags_unreviewed']} high severity)" if s["high_severity_flags_unreviewed"] else ""))
        if s["secrets_unverified"]:
            bits.append(f"{s['secrets_unverified']} of {s['secrets_total']} show secrets are unverified")
        banner(f"⚠️ {WARNING}<br><span style='opacity:.85'>{esc(' · '.join(bits))}.</span>")
    else:
        banner(f"✅ All flags and secrets reviewed. {WARNING}", "info")


def api_error_box() -> None:
    err = st.session_state.pop("_api_error", None)
    if err:
        st.error(err, icon="🔌")


def run_status_pill(run: dict | None) -> str:
    if not run:
        return pill("Not started", "mute")
    s = run["status"]
    kind = {"COMPLETED": "ok", "RUNNING": "warn", "FAILED": "bad", "NOT_STARTED": "mute"}.get(s, "mute")
    label = {"COMPLETED": "Completed", "RUNNING": "Running", "FAILED": "Failed", "NOT_STARTED": "Not started"}.get(s, s)
    return pill(f"● {label}", kind)


def start_run(options: dict | None = None) -> None:
    try:
        r = api.post("/api/process/start", options or {})
        st.session_state["active_run"] = r["run_id"]
        st.toast(f"Started {r['run_id']}", icon="🚀")
    except api.APIError as e:
        st.error(str(e))


def follow_run() -> None:
    """Poll the backend while a run is in progress (progress bar + current stage)."""
    done = st.session_state.pop("_run_done", None)
    if done:
        (st.success if done[0] == "COMPLETED" else st.error)(done[1], icon="✅" if done[0] == "COMPLETED" else "⚠️")
    rid = st.session_state.get("active_run")
    if not rid:
        return
    try:
        r = api._req("GET", f"/api/process/status/{rid}").json()
    except api.APIError as e:
        st.error(str(e))
        return
    if r["status"] in ("RUNNING", "NOT_STARTED"):
        st.progress(r["progress"], text=f"Agents working · {r['stage'] or 'planning'} · {r['progress'] * 100:.0f}%")
        time.sleep(1.0)
        api.get.clear()
        st.rerun()
    else:
        st.session_state.pop("active_run", None)
        api.get.clear()
        msg = (f"Run {rid} completed." if r["status"] == "COMPLETED"
               else f"Run {rid} {r['status'].lower()}: {(r['errors'] or [{}])[-1].get('error', '')}")
        st.session_state["_run_done"] = (r["status"], msg)
        st.rerun()          # redraw the page so the button and metrics reflect the finished run
