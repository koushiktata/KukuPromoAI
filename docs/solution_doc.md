# KukuPromo AI — finding promo cuts in microdrama screenplays
**Problem 1: Find the Promos** · [Name] · [Roll no.] · [Branch] · Prototype: [repo link] · Raw outputs: [private folder link]

## The problem and why I picked it
An editor watches every episode to find promo moments, and a new show ships every week. Problem 1 came with
real input (50 timestamped episodes) and an output that can be checked (exact timestamps). It is also the problem
I'd be asked to run live on a new show in the interview, so I built a reusable tool, not a one-off analysis:
**upload a show's screenplays → get ranked 20–60 s promos with the exact cut points, ready for an editor to approve.**

## Assumptions (where the brief was silent)
- **Timestamps are per episode.** Every cut lands on a real event boundary in the script; nothing is interpolated.
- **Duration = sum of the segments**; gaps between stitched segments don't count.
- **"Hook in 3 s"** = a strong dialogue, action or visual beat starting ≤ 3 s after the first cut.
- **Text only:** I can't see the footage, so visual-only hooks (CAMERA lines) are flagged for a human check.
- **Two audiences:** *new viewers* (cold, no known secret revealed) vs *re-targeting* (twists allowed).
- **Scoring weights** (hook 25 %, cliffhanger 30 %, standalone 20 %, emotion 15 %, coherence 10 %) are my own guess,
  not Kuku's criteria, and can be changed in Settings.

## How it works
`Streamlit UI → FastAPI → orchestrator → 5 agents → typed tools → SQLite`. The orchestrator runs a fixed plan
(213 tasks for 50 episodes). Each task gets up to 2 retries and a JSON checkpoint, so a stopped run resumes, and one
failed episode is escalated to a human instead of killing the run.

| Kept as code / rules | Given to AI (optional) | Kept for humans |
|---|---|---|
| Parsing, cut points, durations, 12 validation checks, de-duplication, ranking, spoiler + content flags | Scoring the 4 best distinct candidates per episode (+ 8 trailers) 1–5 and writing "why it works". One model or a **panel of several** (averaged; big disagreement is flagged). An LLM can't create timestamps: unknown IDs are dropped. | Approve / reject each promo with a reason; verify the AI-written secrets list and content flags |

**Signals, not just keywords:** the writers' emotion tags (*Furious, Shouting*) → intensity; sentiment and sudden
sentiment turns; 14 dramatic labels with confidence; unanswered questions; sound-effect stings; character aliases
(*Mysterious Bearded Man = Alexander*). **Promo shapes:** one continuous clip, two cuts from one episode (skip the slow
middle), or a cross-episode trailer. Near-identical cuts become **alternative cuts** of one moment.

## Results on the full input pack (50/50 episodes, rules only, ~4 s)
801 candidate cuts → 336 pass every rule → **155 distinct promos** (103 fully valid, 339 alternative cuts). 47 are for
new viewers and 31 for re-targeting. Every ranked promo has its hook within 3 s; mean length 37.7 s; 44/50 episodes
have a valid promo. The tool also lists 10 possible show secrets and 93 content flags for review.
**Top pick:** Ep 28 01:16.80–02:16.70. Hook at +2.2 s: *"A witch has no need for family heirlooms in the gallows."*
It ends on *"…before he sends you to the gallows."*, the last spoken line before the cut to black. I checked the top 3
by hand against the raw files: timestamps and source line numbers match.

## How I know it's good, and where it fails
- **Guarantees (60 automated tests):** made-up timestamps → INVALID, wrong order or length rejected, reviews survive
  re-runs, a run cut off by a restart resumes, exports with 0 approved rows, the judge panel survives one failing model.
- **Reference check:** I wrote down 8 must-have moments (the altar betrayal, the proposal, the arsenic discovery, the
  riding-crop strike, the branding iron, the explosion, the Duke reveal, the annulment). With rules only, **7/8 appear
  in the ranking but only 1/8 in the top 30**. The Ep 1 altar betrayal ranks #71, and the Ep 31 branding iron isn't
  found at all (each episode keeps only its 8 strongest hook points). Rules find *intense* moments, not
  *story-defining* ones. That's the job of the LLM judge.
- **LLM judge results: not yet measured.** The real HTTP path is tested end to end against a local fake model
  (18 candidates judged, an invented ID ignored), but not with a real model. Running
  `python scripts/benchmark.py` after saving a key fills in rules vs one LLM vs a panel in `evaluation/benchmark.md`.
  [Paste the table here once it has run.]
- **Known errors:** "You swore you loved me!" (Ep 1) is wrongly listed as a hidden-relationship secret. Some promos
  sit at 59.9 s, the edge of the window. Cross-episode trailers can feel stitched (coherence 3–4/5).

## Scale and cost
Rules only: ~4 s and $0 per 50-episode show. With one LLM: ~51 calls × ~2.5 k tokens ≈ 130 k tokens per show, which
fits free tiers and costs cents on a flash-class model. A 3-model panel costs roughly 3×, but runs in parallel, so the
time barely changes. New shows are uploaded in the app; each one gets its own folder. **How I'd know it works with a
real team:** the approval rate of the top 10, editor minutes saved per show, and install rate of approved promos vs
hand-picked ones. Rejection reasons feed back into the rules and the prompt.

## AI tools I used, and where they got it wrong
[Your tools, e.g. Claude Code for building; Groq / Gemini as judges.] Mistakes caught by tests or by checking the
scripts by hand:
1. The threat detector matched *"hang"* inside *"change"* (fixed with word boundaries).
2. Sentiment silently returned 0.0 for every line (the NLTK lexicon wasn't installed); I added a fallback.
3. The first ranking over-rewarded episode endings and missed the altar betrayal.
4. *"A heavy wet slap"* (a book hitting a puddle) was flagged as violence.
5. A field named `needs_review` made the orchestrator wrongly escalate every validation task (found by the benchmark).
