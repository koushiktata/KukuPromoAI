"""Plotly charts that follow the active light/dark palette."""
from __future__ import annotations

import plotly.graph_objects as go

from components.theme import C

LEGEND = dict(orientation="h", y=-0.12, yanchor="top", x=0, xanchor="left", font=dict(size=11))


def _layout(title: str) -> dict:
    return dict(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                font=dict(color=C["text"], family="Inter"), margin=dict(l=10, r=10, t=44, b=50), height=320,
                title=dict(text=title, font=dict(size=14, color=C["text"])),
                xaxis=dict(gridcolor=C["grid"], zeroline=False), yaxis=dict(gridcolor=C["grid"], zeroline=False),
                hoverlabel=dict(bgcolor=C["surface"], font_color=C["text"], bordercolor=C["secondary"]))


def promos_per_episode(promos: list[dict], n_eps: int) -> go.Figure:
    counts = {e: [0, 0] for e in range(1, n_eps + 1)}
    for p in promos:
        e = p["segments"][0]["episode"]
        if e in counts:
            counts[e][0 if p["category"]["new_viewer"] else 1] += 1
    xs = list(counts)
    fig = go.Figure([
        go.Bar(x=xs, y=[counts[x][0] for x in xs], name="For new viewers",
               marker=dict(color=C["success"], line=dict(width=0))),
        go.Bar(x=xs, y=[counts[x][1] for x in xs], name="Other",
               marker=dict(color=[C["secondary"] if i % 2 else C["fuchsia"] for i in range(len(xs))], line=dict(width=0)))])
    fig.update_layout(**_layout("Ranked promos by starting episode"), barmode="stack", bargap=0.18, legend=LEGEND)
    fig.update_xaxes(title=None, dtick=5)
    return fig


def score_histogram(promos: list[dict]) -> go.Figure:
    fig = go.Figure()
    for kind, col in (("continuous", C["primary"]), ("multi_segment", C["cyan"]), ("cross_episode", C["warning"])):
        xs = [p["scores"]["overall"] for p in promos if p["kind"] == kind]
        if xs:
            fig.add_trace(go.Histogram(x=xs, name=kind.replace("_", " "), marker_color=col, opacity=0.82, nbinsx=16))
    fig.update_layout(**_layout("Overall score by promo type"), barmode="overlay", legend=LEGEND)
    return fig


def task_durations(tasks: list[dict]) -> go.Figure:
    agg: dict[str, float] = {}
    for t in tasks:
        agg[t["stage"]] = agg.get(t["stage"], 0) + t["duration_ms"] / 1000
    xs = sorted(agg)
    colors = [C["secondary"], C["primary"], C["cyan"], C["warning"], C["success"], C["fuchsia"], C["blue"]]
    fig = go.Figure(go.Bar(x=[agg[x] for x in xs], y=xs, orientation="h", marker=dict(color=colors[: len(xs)])))
    fig.update_layout(**_layout("Time per stage (s)"))
    fig.update_yaxes(autorange="reversed")
    return fig
