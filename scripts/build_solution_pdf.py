#!/usr/bin/env python3
"""Build the 2-page solution PDF (docs/KukuPromoAI_solution.pdf) with headless Chrome.

    python scripts/build_solution_pdf.py --repo https://github.com/you/KukuPromoAI \
        --prototype https://your-app-link --outputs "in the same Drive folder as this doc" \
        --why "Your own 2-3 sentences on why you picked this problem."

The benchmark table is filled from evaluation/benchmark.json, so re-run this after scripts/benchmark.py.
"""
from __future__ import annotations

import argparse
import html
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CHROME_CANDIDATES = ["/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
                     "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser",
                     "google-chrome", "chromium", "chromium-browser"]

DEFAULT_WHY = ("Promos are where a show wins or loses a new viewer in three seconds, and today an editor finds them by "
               "watching every episode of every show, with a new show every week. Problem 1 had real input (50 "
               "timestamped episodes) and an answer that can be checked exactly: a timestamp either matches the script "
               "or it doesn't. It is also the problem I'd run live on a new show in the interview, so I built a "
               "reusable tool rather than a one-off analysis.")


def esc(x) -> str:
    return html.escape(str(x))


def link(url: str, label: str) -> str:
    if not url:
        return f"[{label}]"
    if url.startswith("http"):
        return f"<a href='{esc(url)}'>{esc(url)}</a>"
    return esc(url)


def benchmark_rows() -> str:
    """Rows for the judge comparison table, from evaluation/benchmark.json."""
    p = ROOT / "evaluation" / "benchmark.json"
    if not p.exists():
        return ""
    d = json.loads(p.read_text())
    eps = d.get("meta", {}).get("episodes") or "all 50"
    names = {"mock": "rules only", "groq": "rules + Groq judge (gpt-oss-120b)", "gemini": "rules + Gemini judge",
             "groq+gemini": "rules + Groq/Gemini panel"}

    def rank(r, k):
        v = (r.get("reference_ranks") or {}).get(k)
        return f"#{v}" if v else "not found"

    def secs(s):
        return f"{round(s)} s" if (s or 0) < 90 else f"~{round(s / 60)} min"

    return "".join(
        f"<tr><td>{esc(names.get(r['setup'], r['setup']))}</td><td>{esc(eps)}</td><td>{r.get('llm_judged', 0)}</td>"
        f"<td>{r.get('ranked_valid')}</td><td>{rank(r, 'R1')}</td><td>{rank(r, 'R2')}</td><td>{secs(r.get('seconds'))}</td></tr>"
        for r in d.get("results", []) if r.get("status") == "COMPLETED")


def build_html(a) -> str:
    header = (f"<b>Problem chosen:</b> 1, Find the Promos<br>"
              f"<b>Prototype:</b> {link(a.prototype, 'prototype link')} · <b>Code:</b> {link(a.repo, 'repo link')} · "
              f"<b>Raw outputs and video:</b> {link(a.outputs, 'Drive folder link')}")
    who = " · ".join(x for x in (a.name, a.roll, a.branch) if x)
    return f"""<!doctype html><html><head><meta charset="utf-8"><title>KukuPromo AI — Solution</title>
<style>
@page {{ size: A4; margin: 12mm 15mm 11mm 15mm; }}
body {{ font-family: Calibri, Carlito, "Segoe UI", "Helvetica Neue", Arial, sans-serif; font-size: 9.6pt;
       line-height: 1.34; color: #1a1a1a; margin: 0; }}
h1 {{ font-size: 15pt; margin: 0 0 3pt; font-weight: 700; }}
.head {{ font-size: 9pt; margin-bottom: 4pt; }}
h2 {{ font-size: 11.2pt; color: #1f3a5f; margin: 8pt 0 3pt; padding-bottom: 1.5pt; border-bottom: 1px solid #b9c0ca; }}
p {{ margin: 0 0 4pt; text-align: justify; }}
ul, ol {{ margin: 0 0 4pt; padding-left: 15pt; }} li {{ margin: 0 0 1.8pt; }}
code {{ font-family: Menlo, Consolas, monospace; font-size: 8.2pt; background: #f1f3f5; padding: 0 2px; border-radius: 2px; }}
a {{ color: #2456a6; text-decoration: none; }}
table {{ width: 100%; border-collapse: collapse; margin: 2pt 0 4pt; font-size: 8.4pt; break-inside: avoid; }}
th, td {{ border: 1px solid #ccd2da; padding: 2pt 4pt; text-align: left; vertical-align: top; }}
th {{ background: #eef2f7; color: #1f3a5f; }}
tr {{ break-inside: avoid; }}
td:last-child, th:last-child {{ white-space: nowrap; }}
</style></head><body>

<h1>KukuPromo AI: Kuku AI Generalist Assignment</h1>
<div class="head">{header}{('<br>' + esc(who)) if who else ''}</div>

<h2>1. Why this problem</h2>
<p><b>Why this problem.</b> {esc(a.why)}</p>
<p><b>Scope.</b> The tool reads a show's screenplays and returns ranked 20–60 s promos with the exact start and end time
of every segment, plus the hook, the cliffhanger and why it works. It works from the scripts alone, with no video or
audio. A promo is one continuous clip, two cuts from one episode (skipping a slow middle), or a short trailer joining
episode N with N+1 or N+2, because one episode's cliffhanger is picked up in the next. On purpose, it does no video
editing, music, captions or posting, since the brief asks only for the right moments. An editor approves or rejects
each promo and makes the final call. It runs on free tools, and any new show can be uploaded in the web app.</p>

<h2>2. Assumptions (where the brief was silent)</h2>
<ul>
<li>Timestamps are <b>episode-relative</b> (every episode starts at 00:00) and the script times match the final cut
closely enough to cut on.</li>
<li>"Hook in the first 3 seconds" = a strong dialogue, action or visual beat that starts within <b>3.0 s</b> of the
clip start.</li>
<li>Every cut lands on a <b>real event boundary</b> in the script; nothing is interpolated. Promo length = sum of its
segments (20–60 s); gaps between segments don't count.</li>
<li><b>Spoilers</b> and <b>sensitive content</b> are <i>flagged</i>, not removed; the editor decides. Promos that
reveal a secret go to <b>re-targeting</b> existing viewers; the rest can target <b>new viewers</b>. Scoring weights
(hook 25 %, cliffhanger 30 %, standalone 20 %, emotion 15 %, coherence 10 %) are my own guess, not Kuku's criteria.</li>
</ul>

<h2>3. How it works</h2>
<p>Code does everything exact; the AI only judges a shortlist that code has already built and checked.</p>
<ol>
<li><b>Parse (code).</b> 50 screenplays → 3,727 timed events (camera / action / sound / dialogue), each with an ID
like <code>E001-0027</code> and its source line number. Problems are reported, never guessed.</li>
<li><b>Understand (code).</b> The writers' emotion tags (<i>Furious, Shouting</i>) → intensity; sentiment and sudden
sentiment turns; 14 dramatic labels (betrayal, threat, reveal…); unanswered questions; sound stings; character aliases
(<i>Mysterious Bearded Man = Alexander</i>).</li>
<li><b>Find candidates (code).</b> The 8 strongest hook points per episode × every valid cliffhanger cut point →
801 candidate cuts (one clip, two-cut, or cross-episode trailer).</li>
<li><b>Check rules (code).</b> 12 checks: real timestamps, 20–60 s, hook ≤ 3 s, unresolved ending, makes sense alone,
ordered segments, no mid-sentence cut. 336 of 801 pass every rule; failures are marked invalid or sent for review.</li>
<li><b>Judge (AI, optional, 1 call per episode).</b> The model sees the 4 best <i>distinct</i> candidates of an episode
by ID and scores hook / cliffhanger / standalone 1–5 with a one-line reason. <b>It never writes timestamps</b>: unknown
IDs are dropped, and its scores are blended 60/40 with the rules. Several models can judge together as a panel;
scores are averaged and big disagreement is sent to a human.</li>
<li><b>Rank (code).</b> Weighted score; cuts sharing ≥ 50 % of their footage become alternative cuts (801 → 155
promos + 339 alternatives); audience, posting priority, spoiler flags (from an AI-drafted, evidence-linked list of
the show's secrets) and content flags.</li>
<li><b>Agent harness.</b> One orchestrator runs 5 specialised agents through a fixed plan (213 tasks for 50 episodes)
with 2 retries per task, JSON checkpoints, resume after a crash, and a full trace.</li>
<li><b>Human in the loop.</b> In the web app the editor approves or rejects each promo with a reason and exports
approved promos only, or the full <code>ranked.md</code> / CSV. The approval rate is the real quality metric.</li>
</ol>
<p><b>Why this design:</b> scoring every possible window with an AI would take thousands of calls, and a model is bad at
exact arithmetic on timestamps. Code generates and checks the cuts cheaply; the AI is used only where taste matters,
on a shortlist (~51 calls per show).</p>
<p><b>Swappable and reusable:</b> the model is a setting (Groq, Gemini, OpenRouter, OpenAI, Ollama or any
OpenAI-compatible endpoint), keys are added in the app, and a new show is uploaded in the browser, with no
show-specific code.</p>

<h2>4. Scale and cost</h2>
<ul>
<li><b>Rules only:</b> all 50 episodes in about <b>4 s</b>, $0.</li>
<li><b>With the Groq judge</b> (gpt-oss-120b, free tier): 10 episodes in about <b>4 min</b>, 34 cuts judged, 0 errors;
most of that time is free-tier rate limiting. Gemini 3.5 Flash also works but took ~42 s per call in testing.</li>
<li><b>Cost:</b> $0 (free tiers). The real limit is free-tier quota; on a paid tier, episodes can be judged in
parallel, so a show takes minutes.</li>
</ul>

<h2>5. How I know it's good, and where it fails</h2>
<ul>
<li><b>Exactness:</b> every ranked promo's cuts match a real line in the script and its hook starts within 3 s
(100 %). I checked the top 3 by hand against the raw files. 60 automated tests cover the rules, made-up timestamps
(rejected), resume after a crash and the editor workflow.</li>
<li><b>Reference check:</b> I listed 8 moments an editor would surely cut (altar betrayal, proposal, arsenic,
riding crop, branding iron, explosion, Duke reveal, annulment). With rules only, <b>7/8</b> appear in the full-show
ranking but only <b>1/8</b> in the top 30. On episodes 1–10, the AI judge moved both reference moments up:</li>
</ul>
<table>
<tr><th>Judges</th><th>Episodes</th><th>Cuts judged by AI</th><th>Fully valid promos</th><th>Altar betrayal rank</th>
<th>Proposal rank</th><th>Time</th></tr>
<tr><td>rules only</td><td>all 50</td><td>0</td><td>103</td><td>#71</td><td>#40</td><td>~4 s</td></tr>
{benchmark_rows()}
</table>
<ul>
<li><b>Baselines</b> (one clip per episode for every method): the tool's best promo per episode covers <b>2/8</b>
reference moments, a random 30 s clip <b>0/8</b>, and simply the <b>last 30 s of each episode 4/8</b>. The tool beats
random clearly, but loses to episode endings, likely because these writers put their biggest beats right before the
cut.</li>
<li><b>Where it picks badly:</b>
<ol>
<li>Rules rank <i>intense</i> moments above <i>story-defining</i> ones (altar betrayal #71; the Ep 31 branding iron
not found, since each episode keeps only 8 hook points). <i>Partly fixed</i> by the AI judge (#15 → #11 on Ep 1–10);
the full 50-episode AI run is still to do.</li>
<li>My first ranking over-rewarded episode endings, so I cut that bonus; the baseline shows I overcorrected
(endings alone cover 4/8). <i>Not fixed yet:</i> next step is to always add each episode's last 30 s as a candidate
and let the AI judge choose.</li>
<li>"A heavy wet slap" (a book hitting a puddle) was flagged as violence. <i>Fixed:</i> violence words must have a
person as target.</li>
<li>"You swore you loved me!" (Ep 1) is wrongly listed as a hidden-relationship secret. <i>Left to the editor:</i> a
one-minute review of the secrets list.</li>
<li>Visual-only hooks are judged from text. <i>Partly fixed:</i> camera lines count toward the hook and are flagged
for a footage check. Some promos sit at 59.9 s, the edge of the window. <i>Not fixed.</i></li>
</ol></li>
</ul>

<h2>6. AI tools used, and where they got it wrong</h2>
<ul>
<li><b>{esc(a.builder)}:</b> wrote and debugged most of the code with me. <b>Wrong:</b> its threat detector matched
"hang" inside "change"; sentiment silently returned 0.0 for every line (a missing lexicon) until I checked;
a field named <code>needs_review</code> made the orchestrator wrongly escalate every validation step (caught by the
benchmark); and its own test once wrote fake shows into my real data folder.</li>
<li><b>gpt-oss-120b on Groq (judge):</b> the default model name in the code had been retired, and Groq's firewall
blocked Python's default requests (error 1010). Fixed by sending a proper user agent and checking the live model list.</li>
<li><b>Gemini:</b> the default model was closed to new users and the suggested newer one returned "high demand"
errors, so I tested the live list and chose Gemini 3.5 Flash.</li>
</ul>
</body></html>"""


def chrome() -> str:
    for c in CHROME_CANDIDATES:
        if Path(c).exists() or shutil.which(c):
            return c
    sys.exit("Chrome/Chromium not found: open docs/solution.html in a browser and Print → Save as PDF.")


def pages(pdf: Path) -> int:
    return len(re.findall(rb"/Type\s*/Page[^s]", pdf.read_bytes()))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--name", default="")
    ap.add_argument("--roll", default="")
    ap.add_argument("--branch", default="")
    ap.add_argument("--prototype", default="")
    ap.add_argument("--repo", default="")
    ap.add_argument("--outputs", default="")
    ap.add_argument("--why", default=DEFAULT_WHY, help="your own reason for choosing Problem 1")
    ap.add_argument("--builder", default="Claude (Claude Code)", help="the AI coding tool you used")
    ap.add_argument("--out", default=str(ROOT / "docs" / "KukuPromoAI_solution.pdf"))
    a = ap.parse_args()
    html_path = ROOT / "docs" / "solution.html"
    html_path.write_text(build_html(a))
    out = Path(a.out)
    subprocess.run([chrome(), "--headless=new", "--disable-gpu", "--no-pdf-header-footer",
                    f"--print-to-pdf={out}", html_path.as_uri()], check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=120)
    n = pages(out)
    print(f"wrote {out} ({n} page{'s' if n != 1 else ''})")
    if n > 2:
        print("WARNING: more than 2 pages; shorten the text in scripts/build_solution_pdf.py")


if __name__ == "__main__":
    main()
