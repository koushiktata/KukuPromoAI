import streamlit as st

import api_client as api
from components.cards import metric_cards
from components.theme import C, banner, esc, page_header, pill
from views.common import api_error_box

STATUS = {"unreviewed": "Unreviewed", "verified": "✓ Verified", "incorrect": "✕ Incorrect", "needs_review": "⚑ Needs review"}


def _save(sid):
    inv = {v: k for k, v in STATUS.items()}
    try:
        api.post(f"/api/secrets/{sid}/review", {"status": inv[st.session_state[f"sec_{sid}"]],
                                                 "note": st.session_state.get(f"secn_{sid}", ""),
                                                 "reviewer": st.session_state.get("reviewer", "")})
        st.toast("Saved", icon="✅")
    except api.APIError as e:
        st.toast(str(e), icon="⚠️")


def render():
    page_header("Spoilers & Secrets", "What the tool treats as spoilers when it decides which promos are safe for new viewers.")
    api_error_box()
    d = api.safe_get("/api/secrets", {}, {"secrets": [], "disclaimer": ""})
    banner("🤖 <b>AI-generated list.</b> It is built from screenplay lines and loglines and may be incomplete or wrong. "
           "Unverified secrets are not ground truth: mark each one verified, incorrect or needs review.", "info")
    items = d["secrets"]
    by = lambda s: sum(x["review"]["status"] == s for x in items)
    metric_cards([("Secrets found", str(len(items)), "AI-generated", C["secondary"]),
                  ("Verified", str(by("verified")), "confirmed by an editor", C["success"]),
                  ("Incorrect", str(by("incorrect")), "marked wrong by an editor", C["danger"]),
                  ("Unreviewed", str(by("unreviewed") + by("needs_review")), "still to check", C["warning"])])
    with st.expander("🔒 The show's secrets (what the tool treats as spoilers): check once", expanded=True):
        for s in items:
            sid = s["secret_id"]
            if f"sec_{sid}" not in st.session_state:
                st.session_state[f"sec_{sid}"] = STATUS[s["review"]["status"]]
                st.session_state[f"secn_{sid}"] = s["review"].get("note", "")
            with st.container(border=True):
                sev = "bad" if s["severity"] == "high" else "warn" if s["severity"] == "medium" else "mute"
                st.markdown(f"{pill(s['severity'] + ' severity', sev)}{pill('confidence ' + str(s['confidence']), 'info')}"
                            f"{pill('AI-generated', 'mute')} **{esc(s['theme'].replace('_', ' ').title())}** · first in Ep {s['reveal_episode']}",
                            unsafe_allow_html=True)
                st.markdown(esc(s["description"]))
                ev = "".join(f"<li><b>Ep {e['episode']} {esc(e['ts'])}</b> · <span class='kp-muted'>{esc(e['snippet'])}</span></li>"
                             for e in s["evidence"])
                st.markdown(f"<div class='kp-muted'>Screenplay evidence:</div><ul style='margin:.2rem 0 .4rem'>{ev}</ul>",
                            unsafe_allow_html=True)
                c1, c2 = st.columns([1.6, 1.4])
                c1.radio("Verification", list(STATUS.values()), key=f"sec_{sid}", horizontal=True,
                         on_change=_save, args=(sid,), label_visibility="collapsed")
                c2.text_input("Note", key=f"secn_{sid}", placeholder="optional note", on_change=_save, args=(sid,),
                              label_visibility="collapsed")
