# KukuPromo AI — promo cuts from microdrama screenplays

Kuku AI Generalist assignment, **Problem 1: Find the Promos**.
Upload a show's timestamped episode screenplays → get ranked **20–60 s promos** with the exact cut points
(episode + start/end of every segment), the hook, the cliffhanger, why it works, an audience, spoiler and content
flags, and an editor approve/reject workflow with exports.

```
Streamlit (8 pages) ──HTTP──► FastAPI ──► Orchestrator ──► 5 agents ──► typed tools
                                              │   (screenplay · discovery · validation · scoring · quality)
                                              ├─ fixed plan (213 tasks for 50 episodes) · 2 retries/task
                                              ├─ JSON checkpoints · resume · interrupted-run recovery · trace
                                              ├─ judges: offline rules, one LLM, or a panel of several LLMs
                                              └─► SQLite (results, reviews, secrets, flags, traces) ──► exports
```

## Run it
Use the Python that has the packages installed. On this Mac that's Anaconda: `/opt/anaconda3/bin/python`.
```bash
pip install -r requirements.txt
```
Terminal 1, the backend (from the project root):
```bash
python -m uvicorn backend.main:app --port 8000
```
Terminal 2, the frontend:
```bash
python -m streamlit run frontend/app.py
```
Open http://localhost:8501. API docs: http://localhost:8000/docs.

## Use it
1. **Overview → 📤 Upload a show:** name it, select all the episode `.txt` files, click **Upload & find promos**.
   (Or pick a saved show and click **Find Promos**. The original pack goes in `data/scripts/` as the default show.)
2. Results appear underneath: status, metrics, editor review + downloads, then **For new viewers / Re-targeting** tabs.
   Each card has the segments in order, the hook and cliffhanger with timestamps, why it works, why this rank,
   an alternative cut, and **Approve / Reject**.
3. **Settings → Judges:** *Offline (mock)* = rules only, free and instant. *LLM judges* = pick one or more of Groq,
   Gemini, OpenRouter, OpenAI, Ollama. Paste each key once (it's saved to the git-ignored `.env`, write-only, never
   shown again). Several models form a **judge panel**: scores are averaged and disagreement is flagged.
4. Downloads: approved promos only, all promos + decisions (CSV), full report (`ranked.md`).

## Benchmark: rules vs LLM judges
```bash
python scripts/benchmark.py                           # mock, groq, gemini, groq+gemini (skips any without a key)
python scripts/benchmark.py --setups mock groq --episodes 1-10
```
Each setup runs in its own temp folder and database, so the app's results are untouched. Writes
`evaluation/benchmark.md` with reference-moment recall and the rank of each must-have moment.

## Tests
They use synthetic screenplays and temp folders, never the confidential pack or your `.env`:
```bash
python -m pytest -q tests
```

## How it works
| Step | Done by | Notes |
|---|---|---|
| Parse | code (regex) | events with start/end, speaker, emotion tags and **source line** |
| Understand | NLP | emotion tags → intensity, sentiment (NLTK VADER if installed, else built-in), 14 dramatic labels, unanswered questions, character aliases, relationships |
| Discover | code | hook candidates × cliffhanger cut points → continuous / two-part / cross-episode cuts, **only on real event boundaries** |
| Judge | rules, LLM or LLM panel | an LLM scores code-made candidates 1–5; it can't create timestamps; blended 60 % LLM / 40 % rules |
| Validate | code | 12 checks: episode, real timestamps, order, 20–60 s (gaps not counted), hook ≤ 3 s, unresolved ending, standalone, source refs, no mid-line cut |
| Rank | code | weighted score (**our assumption**), duplicates → alternative cuts, posting priority |
| Review | humans | approve / reject; verify AI-written secrets and content flags; stored in SQLite under stable IDs |

## Confidentiality
`data/scripts/`, `data/shows/`, `outputs/` and `.env` are git-ignored. Share raw outputs only through the private
submission form.

## Known limits
- With rules only, 7/8 must-have moments are found but only 1/8 makes the top 30. LLM judging is the fix; it's wired
  and tested against a fake local model, but not yet measured with a real model (see Benchmark).
- Text only: visual-only hooks are flagged for a footage check.
- The secrets list and content flags are pattern-based and need editor verification (known false positive:
  "You swore you loved me!").
