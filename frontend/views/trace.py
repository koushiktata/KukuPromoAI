import pandas as pd
import streamlit as st

import api_client as api
from components.charts import task_durations
from components.theme import C, esc, page_header, pill
from views.common import api_error_box

ICON = {"COMPLETED": "✅", "RUNNING": "⏳", "FAILED": "❌", "NEEDS_REVIEW": "⚑", "PENDING": "○"}


def render():
    page_header("Agent Execution Trace", "One orchestrator, five specialised agents, registered tools, retries and checkpoints.")
    api_error_box()
    runs = api.safe_get("/api/process/runs", {"limit": 20}, [])
    if not runs:
        st.info("No runs yet.")
        return
    # default to the newest run that actually did work (a run that failed at setup has nothing to show)
    default = next((i for i, r in enumerate(runs) if r["status"] in ("RUNNING", "COMPLETED")), 0)
    icon = {"COMPLETED": "✅", "RUNNING": "⏳", "FAILED": "❌"}
    rid = st.selectbox("Run", [r["run_id"] for r in runs], index=default,
                       format_func=lambda x: next(f"{icon.get(r['status'], '○')} {x} · {r['status'].lower()}"
                                                  f" · {r['config'].get('provider', 'mock')}" for r in runs if r["run_id"] == x))
    failed_setup = [r for r in runs[:default] if r["status"] == "FAILED"]
    if failed_setup:
        st.caption("Newer failed run(s): " + "; ".join(f"{r['run_id']}: {(r['errors'] or [{}])[-1].get('error', '')}"
                                                      for r in failed_setup))
    d = api.safe_get(f"/api/agents/status/{rid}")
    if not d:
        return
    done_pct = f"{d['progress'] * 100:.0f}% done"
    st.markdown(pill(rid, "mute") + pill(d["status"], "ok" if d["status"] == "COMPLETED" else "warn")
                + pill(done_pct, "info"), unsafe_allow_html=True)
    # stage stepper
    stages: dict[str, list] = {}
    for t in d["tasks"]:
        stages.setdefault(t["stage"], []).append(t["status"])
    cells = ""
    for name, sts in stages.items():
        done = all(s in ("COMPLETED", "NEEDS_REVIEW") for s in sts)
        running = any(s == "RUNNING" for s in sts)
        cls = "done" if done else "run" if running else ""
        cells += (f'<div class="kp-step {cls}"><b>{esc(name)}</b><div class="s">'
                  f'{sum(s == "COMPLETED" for s in sts)}/{len(sts)} done'
                  f'{" · " + str(sum(s == "NEEDS_REVIEW" for s in sts)) + " escalated" if "NEEDS_REVIEW" in sts else ""}</div></div>')
    st.markdown(f'<div class="kp-stepper">{cells}</div>', unsafe_allow_html=True)

    accents = [C["secondary"], C["primary"], C["cyan"], C["success"], C["warning"], C["fuchsia"]]
    cards = "".join(
        f"<div class='kp-card' style='--accent:{acc}'>"
        f"<div class='lbl'>{esc(a['agent'].replace('_', ' '))}</div>"
        f"<div class='val' style='font-size:1.35rem'>{a['COMPLETED']}/{a['tasks']}</div>"
        f"<div class='sub'>{esc(a['role'])}</div>"
        f"<div class='sub'>retries {a['retries']} · {a['ms'] / 1000:.1f}s"
        f"{' · ' + str(a['NEEDS_REVIEW']) + ' escalated' if a['NEEDS_REVIEW'] else ''}"
        f"{' · ' + str(a['FAILED']) + ' failed' if a['FAILED'] else ''}</div></div>"
        for a, acc in zip(d["agents"], accents))
    st.markdown(f"<div class='kp-grid' style='grid-template-columns:repeat(auto-fit,minmax(200px,1fr))'>{cards}</div>",
                unsafe_allow_html=True)
    if d["escalations"]:
        st.warning("Escalated to a human: " + "; ".join(f"{e['task_id']}: {e['reason']}" for e in d["escalations"][:5]))
    if d["errors"]:
        st.error("Errors: " + "; ".join(f"{e['task_id']}: {e['error']}" for e in d["errors"][-5:]))

    c1, c2 = st.columns([1, 1.3])
    with c1:
        st.plotly_chart(task_durations(d["tasks"]), use_container_width=True, config={"displayModeBar": False})
    with c2:
        tdf = pd.DataFrame([{"": ICON.get(t["status"], ""), "Task": t["task_id"], "Agent": t["agent"].replace("_agent", ""),
                             "Tool": t["tool"], "Status": t["status"], "Tries": t["attempts"],
                             "ms": t["duration_ms"], "Error": t["error"]} for t in d["tasks"]])
        st.dataframe(tdf, hide_index=True, use_container_width=True, height=300)

    st.markdown("#### Activity log")
    tr = api.safe_get(f"/api/agents/trace/{rid}", {"limit": 5000}, {"events": []})["events"]
    q = st.text_input("Filter log", placeholder="agent, tool or status, e.g. judge_promos / retry / ERROR")
    ev = [e for e in tr if not q or q.lower() in " ".join(str(v) for v in e.values()).lower()]
    df = pd.DataFrame([{"#": e["seq"], "At": e["at"][11:19], "Agent": e["agent"], "Action": e["action"],
                        "Tool": e["tool"], "Status": e["status"], "ms": e["duration_ms"], "Detail": e["detail"]}
                       for e in ev[-400:]][::-1])
    st.dataframe(df, hide_index=True, use_container_width=True, height=380)
    st.caption(f"{len(tr)} trace events · newest first · showing last {min(400, len(ev))}")
