"""Metric cards, promo cards and the editor review control."""
from __future__ import annotations

import streamlit as st

import api_client as api
from components.theme import C, esc, pill

DECISIONS = {"not_reviewed": "○ Not reviewed", "approved": "✓ Approve", "rejected": "✕ Reject"}
STATUS_PILL = {"VALID": ("Valid", "ok"), "NEEDS_REVIEW": ("Needs review", "warn"), "INVALID": ("Invalid", "bad")}
CRIT = [("hook", "Hook"), ("cliffhanger", "Cliffhanger"), ("standalone", "Makes sense alone"),
        ("emotion", "Emotional intensity"), ("coherence", "Narrative coherence")]


def metric_cards(items: list[tuple[str, str, str, str]]) -> None:
    """items: (label, value, sub, accent color)"""
    cells = "".join(
        f'<div class="kp-card" style="--accent:{acc}"><div class="lbl">{esc(l)}</div>'
        f'<div class="val">{esc(v)}</div><div class="sub">{esc(s)}</div></div>'
        for l, v, s, acc in items)
    st.markdown(f'<div class="kp-grid">{cells}</div>', unsafe_allow_html=True)


def review_metrics(stats: dict) -> None:
    rate = "—" if stats.get("approval_rate") is None else f"{stats['approval_rate'] * 100:.0f}%"
    metric_cards([
        ("Reviewed", f"{stats['reviewed']} / {stats['total']}", f"{stats['not_reviewed']} still to check", C["secondary"]),
        ("Approved", str(stats["approved"]), "ready to post", C["success"]),
        ("Rejected", str(stats["rejected"]), "won't post", C["danger"]),
        ("Approval rate", rate, "approved ÷ reviewed" if stats["reviewed"] else "no decisions yet", C["warning"]),
    ])


def timestamp_table(promos: list[dict], height: int | None = None) -> None:
    """The core answer: where to cut each promo (episode, start, end), best first."""
    import pandas as pd
    if not promos:
        st.info("No promos match.")
        return
    rows = []
    for p in promos:
        segs = p["segments"]
        cut = "  →  ".join(f"Ep {s['episode']}  {s['start_ts']} – {s['end_ts']}" for s in segs)
        rows.append({
            "Rank": p.get("rank"), "Priority": (p.get("posting_priority") or "").split(" · ")[0],
            "Cut these timestamps (in order)": cut, "Length (s)": round(p["duration"]),
            "Hook (first 3s)": p["hook"]["text"] if p.get("hook") else "",
            "Ends on (cliffhanger)": p["cliffhanger"]["text"] if p.get("cliffhanger") else "",
            "Score /5": p["scores"]["overall"],
            "Audience": "New viewers" if p["category"]["new_viewer"] else "Re-targeting" if p["category"]["retarget"] else "—",
            "Judges": (p["judge"].get("agreement") or "").capitalize() + " agreement" if p["judge"].get("panel")
            else (p["judge"].get("provider") or "").split(":")[0],
        })
    st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True,
                 height=height or min(560, 38 + 35 * len(rows)),
                 column_config={
                     "Rank": st.column_config.NumberColumn(width="small"),
                     "Cut these timestamps (in order)": st.column_config.TextColumn(width="large"),
                     "Length (s)": st.column_config.NumberColumn(width="small"),
                     "Score /5": st.column_config.ProgressColumn(min_value=1, max_value=5, format="%.2f", width="small"),
                     "Hook (first 3s)": st.column_config.TextColumn(width="medium"),
                     "Ends on (cliffhanger)": st.column_config.TextColumn(width="medium")})


HOOK_WHAT = {"betrayal": "a public betrayal", "humiliation": "the heroine is humiliated", "violence": "physical danger",
             "threat": "a life-or-death threat", "revelation": "a secret starts to come out",
             "confrontation": "a heated face-off", "unexpected_arrival": "someone bursts in",
             "power_shift": "the power suddenly flips", "emotional_breakdown": "raw emotion",
             "revenge": "a vow of revenge", "turn": "a sharp emotional turn"}
CLIFF_WHAT = {"unanswered_question": "a question left hanging", "suspense": "a held, unresolved beat",
              "threat": "a threat that hasn't played out", "unexpected_arrival": "an arrival we don't see resolved",
              "revelation": "a reveal with no reaction yet", "violence": "violence about to land",
              "power_shift": "a power shift mid-swing", "confrontation": "a stand-off with no winner yet"}


def _what(moment: dict, table: dict) -> str:
    labs = sorted((moment.get("labels") or {}).items(), key=lambda kv: -kv[1])
    return next((table[k] for k, _ in labs if k in table), "")


def compact_promo_card(p: dict, expanded: bool = False, key_prefix: str = "") -> None:
    """Reference-style card: segments, hook, cliffhanger, why it works, why this rank, alternative cut, decision."""
    eps = []
    for s in p["segments"]:
        if not eps or eps[-1] != s["episode"]:
            eps.append(s["episode"])
    dec = {"approved": "  ✓", "rejected": "  ✕"}.get(p["review"]["decision"], "")
    title = f"#{p['rank']} · Ep {' → '.join(map(str, eps))} · {p['duration']:.0f}s · score {p['scores']['overall']:.2f}{dec}"
    with st.expander(title, expanded=expanded):
        segs = " → ".join(f"Ep{s['episode']} {s['start_ts']}–{s['end_ts']}" for s in p["segments"])
        st.markdown(f"**Segments (in order):** {segs}")
        h, c = p.get("hook"), p.get("cliffhanger")
        if h:
            what = _what(h, HOOK_WHAT)
            st.markdown(f"**Hook** (Ep{h['episode']} {h['ts']}): {esc(what.capitalize() + '.' if what else h['text'])}")
            st.markdown(f"> *“{esc(h['text'])}”*")
        if c:
            what = _what(c, CLIFF_WHAT)
            st.markdown(f"**Cliffhanger** (Ep{c['episode']} {c['ts']}): {esc(what.capitalize() + '.' if what else c['text'])}")
            st.markdown(f"> *“{esc(c['text'])}”*")
        st.markdown(f"**Why it works:** {esc(p.get('why_it_works', ''))}")
        sc, j = p["scores"], p.get("judge", {})
        comment = (j.get("comment") or "").strip()
        if comment.lower().startswith((j.get("verdict") or "").lower() + ":"):
            comment = comment[len(j["verdict"]) + 1:].strip()          # avoid "Postable – Postable: ..."
        judge = f" *Judge: {esc(j['verdict'])} – {esc(comment)}*" if j.get("verdict") else ""
        st.markdown(f"**Why rank #{p['rank']}:** hook {sc['hook']:.0f}/5 · cliffhanger {sc['cliffhanger']:.0f}/5 · "
                    f"makes sense alone {sc['standalone']:.0f}/5.{judge}" + judge_panel(j), unsafe_allow_html=True)
        alts = p.get("alternatives") or []
        if alts:
            a = alts[0]
            a_segs = " → ".join(f"Ep{s['episode']} {s['start_ts']}–{s['end_ts']}" for s in a["segments"])
            st.caption(f"Alternative cut of the same moment: {a_segs} ({a['duration']:.0f}s, score {a['overall']:.2f})")
        if p["category"].get("spoiler_secret_ids"):
            st.caption("⚠ Contains a possible spoiler — check the show's secrets before posting.")
        review_control(p, key_prefix)


def judge_panel(j: dict) -> str:
    """Per-model scores when several LLMs judged the promo."""
    if not j.get("panel"):
        return ""
    agr = j.get("agreement") or ""
    kind = {"high": "ok", "medium": "warn", "low": "bad"}.get(agr, "mute")
    parts = [pill(f"{agr} agreement", kind)] if agr else []
    for m in j["panel"]:
        score = f" {m['overall']:.1f}/5" if m.get("overall") is not None else ""
        parts.append(pill(f"{m['model'].split(':')[0]}{score}" + (f" · {m['verdict']}" if m.get("verdict") else ""), "info"))
    return "<div style='margin:.2rem 0 .4rem'>⚖️ " + "".join(parts) + "</div>"


def _eps(p: dict) -> str:
    eps = []
    for s in p["segments"]:
        if not eps or eps[-1] != s["episode"]:
            eps.append(s["episode"])
    return " → ".join(str(e) for e in eps)


def promo_title(p: dict) -> str:
    rank = f"#{p['rank']}" if p.get("rank") else "—"
    dec = {"approved": "  ✓ approved", "rejected": "  ✕ rejected"}.get(p["review"]["decision"], "")
    return f"{rank} · Ep {_eps(p)} · {p['duration']:.0f}s · Score {p['scores']['overall']:.2f}  ·  {p.get('posting_priority', '')}{dec}"


def _save_review(pid: str, k_dec: str, k_rsn: str, k_seen: str) -> None:
    dec = st.session_state.get(k_dec)
    reason = st.session_state.get(k_rsn, "")
    inv = {v: k for k, v in DECISIONS.items()}
    decision = inv.get(dec, "not_reviewed")
    try:
        api.post(f"/api/promos/{pid}/review", {"decision": decision, "reason": reason,
                                               "reviewer": st.session_state.get("reviewer", "")})
        st.session_state[k_seen] = (decision, reason)
        st.toast("Decision saved", icon="✅")
    except api.APIError as e:
        st.toast(f"Could not save: {e}", icon="⚠️")


def review_control(p: dict, key_prefix: str = "") -> None:
    """The same promo can appear in several tabs, so widget keys include the tab prefix.
    Each copy re-syncs from the backend whenever the saved decision changed elsewhere."""
    pid = p["promo_id"]
    k_dec, k_rsn, k_seen = f"dec_{key_prefix}_{pid}", f"rsn_{key_prefix}_{pid}", f"seen_{key_prefix}_{pid}"
    server = (p["review"]["decision"], p["review"].get("reason", ""))
    if st.session_state.get(k_seen) != server:
        st.session_state[k_dec] = DECISIONS.get(server[0], DECISIONS["not_reviewed"])
        st.session_state[k_rsn] = server[1]
        st.session_state[k_seen] = server
    c1, c2 = st.columns([1.1, 1.6])
    with c1:
        st.radio("Editor decision", list(DECISIONS.values()), key=k_dec, horizontal=True,
                 on_change=_save_review, args=(pid, k_dec, k_rsn, k_seen))
    with c2:
        st.text_input("Reason (optional)", key=k_rsn, placeholder="e.g. spoils the twist / hook too slow / great opener",
                      on_change=_save_review, args=(pid, k_dec, k_rsn, k_seen))


def score_bars(sc: dict) -> str:
    rows = "".join(
        f'<div class="kp-bar"><span class="n">{n}</span><span class="track"><span class="fill" '
        f'style="width:{max(0, min(100, (sc[k] - 1) / 4 * 100)):.0f}%"></span></span><span class="v">{sc[k]:.1f}</span></div>'
        for k, n in CRIT)
    return rows


def promo_card(p: dict, flags_by_id: dict, secrets_by_id: dict, expanded: bool = False, key_prefix: str = "") -> None:
    with st.expander(promo_title(p), expanded=expanded):
        stt, kind = STATUS_PILL.get(p["validation"]["status"], ("?", "mute"))
        cat = p["category"]
        pills = pill(stt, kind) + pill(p["kind"].replace("_", " "), "info")
        if cat["new_viewer"]:
            pills += pill("For new viewers", "ok")
        if cat["retarget"]:
            pills += pill("Re-targeting", "pri")
        if cat["spoiler_secret_ids"]:
            pills += pill(f"⚠ spoiler ×{len(cat['spoiler_secret_ids'])}", "warn")
        nflags = len(p.get("content_flag_ids", []))
        if nflags:
            pills += pill(f"content flags ×{nflags}", "bad" if any(
                flags_by_id.get(f, {}).get("severity") == "high" for f in p["content_flag_ids"]) else "warn")
        if p.get("needs_human_review"):
            pills += pill("human check advised", "warn")
        st.markdown(pills, unsafe_allow_html=True)

        segs = '<span class="kp-arrow">→</span>'.join(
            f'<span class="kp-seg">Ep{s["episode"]} {s["start_ts"]}–{s["end_ts"]}</span>' for s in p["segments"])
        st.markdown(f'<div class="kp-muted" style="margin:.4rem 0 .2rem">Segments (in order)</div>{segs}',
                    unsafe_allow_html=True)

        left, right = st.columns([1.35, 1])
        with left:
            h, c = p.get("hook"), p.get("cliffhanger")
            if h:
                st.markdown(f'<div class="kp-quote" style="--q:{C["primary"]}"><div class="k">Hook · Ep{h["episode"]} '
                            f'{h["ts"]}</div><div class="t">{esc(h["text"])}</div></div>', unsafe_allow_html=True)
            if c:
                st.markdown(f'<div class="kp-quote" style="--q:{C["secondary"]}"><div class="k">Cliffhanger · '
                            f'Ep{c["episode"]} {c["ts"]}</div><div class="t">{esc(c["text"])}</div></div>',
                            unsafe_allow_html=True)
            st.markdown(f"**Why it works:** {esc(p.get('why_it_works', ''))}")
            j = p.get("judge", {})
            if j.get("verdict"):
                label = "Judge panel" if j.get("panel") else "Judge"
                st.markdown(f"**{label}** <span class='kp-muted'>({esc(j.get('provider', ''))})</span>: "
                            f"{esc(j.get('comment') or j['verdict'])}" + judge_panel(j), unsafe_allow_html=True)
        with right:
            st.markdown(f'<div class="kp-muted" style="margin-bottom:.3rem">Score breakdown · {esc(p["scores"]["source"])}</div>'
                        + score_bars(p["scores"]), unsafe_allow_html=True)
            st.markdown(f"<div class='kp-muted' style='margin-top:.5rem'><b>Why this rank:</b> {esc(p.get('rank_reason', ''))}</div>",
                        unsafe_allow_html=True)
            st.markdown(f"<div class='kp-muted' style='margin-top:.3rem'><b>Audience:</b> {esc(cat['explanation'])}</div>",
                        unsafe_allow_html=True)

        tabs = st.tabs([f"Alternative cuts ({len(p.get('alternatives', []))})", "Validation",
                        f"Spoilers & flags ({len(cat['spoiler_secret_ids']) + nflags})", "Transcript"])
        with tabs[0]:
            if not p.get("alternatives"):
                st.caption("No alternative cut of this moment.")
            for a in p.get("alternatives", []):
                segs_a = " → ".join(f"Ep{s['episode']} {s['start_ts']}–{s['end_ts']}" for s in a["segments"])
                st.markdown(f"<span class='kp-seg'>{esc(segs_a)}</span> {a['duration']:.0f}s · score **{a['overall']:.2f}** "
                            f"{pill('valid', 'ok') if a['valid'] else pill('needs review', 'warn')}<br>"
                            f"<span class='kp-muted'>{esc(a['difference'])}</span>", unsafe_allow_html=True)
        with tabs[1]:
            for ck in p["validation"]["checks"]:
                icon = "✅" if ck["passed"] else ("❌" if ck["severity"] == "hard" else "⚠️")
                st.markdown(f"{icon} `{ck['name']}` <span class='kp-muted'>{esc(ck['detail'])}</span>", unsafe_allow_html=True)
            if p.get("quality_notes"):
                st.markdown("**Quality reviewer:** " + " · ".join(esc(n) for n in p["quality_notes"]), unsafe_allow_html=True)
        with tabs[2]:
            if not cat["spoiler_secret_ids"] and not nflags:
                st.caption("No spoiler or content flags detected. That does not mean the clip is safe: check it before posting.")
            for sid in cat["spoiler_secret_ids"]:
                s = secrets_by_id.get(sid)
                if s:
                    st.markdown(f"{pill(s['severity'] + ' spoiler', 'warn')} **{esc(s['theme'])}** · reveal Ep {s['reveal_episode']} · "
                                f"review: {esc(s['review']['status'])}", unsafe_allow_html=True)
            for fid in p.get("content_flag_ids", []):
                f = flags_by_id.get(fid)
                if f:
                    k = "bad" if f["severity"] == "high" else "warn" if f["severity"] == "medium" else "mute"
                    st.markdown(f"{pill(f['flag_type'].replace('_', ' '), k)} Ep{f['episode']} {f['ts']} · "
                                f"<span class='kp-muted'>{esc(f['snippet'])}</span> · review: {esc(f['review']['status'])}",
                                unsafe_allow_html=True)
        with tabs[3]:
            if st.toggle("Load transcript for this promo", key=f"tr_{key_prefix}{p['promo_id']}"):
                d = api.safe_get(f"/api/promos/{p['promo_id']}", {"include_transcript": "true"}, {})
                for seg in d.get("transcript", []):
                    st.markdown(f"**Segment {seg['segment']} · Episode {seg['episode']}**")
                    st.code("\n".join(f"[{l['ts']:>7}] {l['who']}: {l['text']}" for l in seg["lines"]), language=None)
        st.divider()
        review_control(p, key_prefix)
