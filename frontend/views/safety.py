import pandas as pd
import streamlit as st

import api_client as api
from components.cards import metric_cards
from components.theme import C, banner, page_header
from views.common import api_error_box

LABEL = {"unreviewed": "Unreviewed", "verified": "Verified", "incorrect": "Incorrect", "needs_review": "Needs review"}


def render():
    page_header("Content Safety", "Possible graphic, sexual, threatening or otherwise sensitive content in the source scenes.")
    api_error_box()
    banner("⚠️ These are <b>content-review signals</b>, not legal or platform-policy decisions. "
           "A promo with no flags is <b>not</b> automatically safe: watch it before posting.")
    c1, c2, c3 = st.columns(3)
    scope = c1.radio("Scope", ["In ranked promos", "Whole show"], horizontal=True)
    sev = c2.selectbox("Severity", ["all", "high", "medium", "low"])
    stat = c3.selectbox("Review status", ["all", "unreviewed", "verified", "incorrect", "needs_review"],
                        format_func=lambda x: "All" if x == "all" else LABEL[x])
    d = api.safe_get("/api/content-flags", {"severity": sev, "status": stat,
                                            "in_ranked_promos": str(scope == "In ranked promos").lower()}, {"flags": []})
    flags = d["flags"]
    unrev = sum(f["review"]["status"] in ("unreviewed", "needs_review") for f in flags)
    metric_cards([("Flags", str(len(flags)), scope.lower(), C["secondary"]),
                  ("High severity", str(sum(f["severity"] == "high" for f in flags)), "violence / abuse", C["danger"]),
                  ("Unreviewed", str(unrev), "need a human look", C["warning"]),
                  ("Verified", str(sum(f["review"]["status"] == "verified" for f in flags)), "confirmed", C["success"])])
    if not flags:
        st.info("No flags for this filter.")
        return
    df = pd.DataFrame([{"flag_id": f["flag_id"], "Type": f["flag_type"].replace("_", " "), "Episode": f["episode"],
                        "Time": f["ts"], "Evidence": f["snippet"], "Severity": f["severity"],
                        "Confidence": f["confidence"], "Review": LABEL[f["review"]["status"]]} for f in flags])
    edited = st.data_editor(
        df, hide_index=True, use_container_width=True, height=min(600, 40 + 35 * len(df)), key="flag_editor",
        disabled=["flag_id", "Type", "Episode", "Time", "Evidence", "Severity", "Confidence"],
        column_config={"flag_id": None,
                       "Review": st.column_config.SelectboxColumn("Review", options=list(LABEL.values()), required=True),
                       "Confidence": st.column_config.ProgressColumn("Confidence", min_value=0, max_value=1, format="%.2f"),
                       "Evidence": st.column_config.TextColumn("Evidence", width="large")})
    inv = {v: k for k, v in LABEL.items()}
    changed = edited[edited["Review"] != df["Review"]]
    if len(changed):
        for _, row in changed.iterrows():
            try:
                api.post(f"/api/content-flags/{row['flag_id']}/review", {"status": inv[row["Review"]],
                                                                          "reviewer": st.session_state.get("reviewer", "")})
            except api.APIError as e:
                st.error(str(e))
        st.toast(f"Saved {len(changed)} review(s)", icon="✅")
        st.session_state.pop("flag_editor", None)
        st.rerun()
