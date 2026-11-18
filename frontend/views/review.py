import streamlit as st

from components.cards import review_control, review_metrics
from components.theme import esc, page_header, pill
from views.common import api_error_box, promos, summary

FILTERS = {"All promos": "all", "Not reviewed": "not_reviewed", "Approved": "approved", "Rejected": "rejected"}


def render():
    page_header("Editor Review", "Approve or reject each promo. Decisions are saved to the backend immediately and survive restarts.")
    api_error_box()
    s = summary()
    if not s or not s["ranked"]:
        st.info("Run the pipeline first.")
        return
    review_metrics(s["review"])
    c1, c2 = st.columns([2, 1])
    choice = c1.radio("Filter", list(FILTERS), horizontal=True, label_visibility="collapsed")
    st.session_state["reviewer"] = c2.text_input("Reviewer name (optional)", st.session_state.get("reviewer", ""),
                                                 placeholder="e.g. Priya (promo team)")
    data = promos(decision=FILTERS[choice])["promos"]
    if not data:
        st.info("Nothing here yet.")
    for p in data[:60]:
        segs = " → ".join(f"Ep{x['episode']} {x['start_ts']}–{x['end_ts']}" for x in p["segments"])
        cat = (pill("new viewers", "ok") if p["category"]["new_viewer"] else "") + \
              (pill("re-targeting", "pri") if p["category"]["retarget"] else "")
        with st.container(border=True):
            st.markdown(f"<b>#{p['rank']}</b> · <span class='kp-seg'>{esc(segs)}</span> {p['duration']:.0f}s · "
                        f"score <b>{p['scores']['overall']:.2f}</b> · {esc(p.get('posting_priority', ''))} {cat}<br>"
                        f"<span class='kp-muted'>Hook: {esc(p['hook']['text'][:120])}<br>Cliffhanger: "
                        f"{esc(p['cliffhanger']['text'][:120])}</span>", unsafe_allow_html=True)
            review_control(p, "rv")
    if len(data) > 60:
        st.caption(f"Showing 60 of {len(data)}. Use the filters or Promo Discovery for the rest.")
