import streamlit as st

from components.cards import promo_card, timestamp_table
from components.theme import page_header
from views.common import api_error_box, lookups, posting_warning, promos, summary

SORTS = {"Posting priority": None, "Overall score": "score", "Duration": "duration", "Episode": "episode"}
PRIORITY_ORDER = ["P1", "P2", "Retargeting", "P3", "Hold", "Do not"]


def _sort(items, how):
    if how == "score":
        return sorted(items, key=lambda p: -p["scores"]["overall"])
    if how == "duration":
        return sorted(items, key=lambda p: p["duration"])
    if how == "episode":
        return sorted(items, key=lambda p: (p["segments"][0]["episode"], p["segments"][0]["start"]))
    return sorted(items, key=lambda p: (next((i for i, k in enumerate(PRIORITY_ORDER)
                                              if p.get("posting_priority", "").startswith(k)), 9), p.get("rank") or 999))


def render():
    page_header("Promo Discovery", "Ranked promos split by audience. Every timestamp is checked against the screenplay.")
    api_error_box()
    s = summary()
    posting_warning(s)
    allp = promos()
    counts = allp["category_counts"]
    f1, f2, f3, f4, f5 = st.columns([1.2, 1, 1, 1, 0.9])
    sort = SORTS[f1.selectbox("Sort by", list(SORTS))]
    ep_opts = ["All"] + sorted({x["episode"] for p in allp["promos"] for x in p["segments"]})
    ep = f2.selectbox("Episode", ep_opts)
    status = f3.selectbox("Validation", ["all", "VALID", "NEEDS_REVIEW", "INVALID"],
                          format_func=lambda x: {"all": "All", "VALID": "Valid", "NEEDS_REVIEW": "Needs review",
                                                 "INVALID": "Invalid"}[x])
    decision = f4.selectbox("Review", ["all", "not_reviewed", "approved", "rejected"],
                            format_func=lambda x: x.replace("_", " ").capitalize())
    limit = f5.number_input("Show", 5, 200, 20, step=5)
    base = {"status": status, "decision": decision, "episode": None if ep == "All" else ep}
    view = st.segmented_control("View", ["🗂 Cards", "⏱ Timestamp table"], default="🗂 Cards", key="disc_view",
                                label_visibility="collapsed") or "🗂 Cards"
    flags, secrets = lookups()
    t1, t2, t3 = st.tabs([f"🆕 For new viewers ({counts['new_viewer']})", f"🔁 Re-targeting / spoilers ({counts['retarget']})",
                          f"All ranked ({allp['count']})"])
    for tab, cat, key in ((t1, "new_viewer", "nv"), (t2, "retarget", "rt"), (t3, "all", "all")):
        with tab:
            data = _sort(promos(category=cat, **base)["promos"], sort)
            if cat == "retarget":
                st.caption("For existing viewers. These may reveal twists: spoiler labels are AI-generated and must be verified.")
            if cat == "new_viewer":
                st.caption("Cold-audience promos: strong hook, understandable alone, no known secret revealed.")
            if not data:
                st.info("No promos match these filters.")
                continue
            if view.startswith("⏱"):
                timestamp_table(data[: int(limit)])
                continue
            for i, p in enumerate(data[: int(limit)]):
                promo_card(p, flags, secrets, expanded=(i == 0 and key == "nv"), key_prefix=key)
            if len(data) > limit:
                st.caption(f"Showing {int(limit)} of {len(data)}. Increase 'Show' to see more.")
