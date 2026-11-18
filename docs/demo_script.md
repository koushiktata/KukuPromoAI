# 3-minute walkthrough plan

**Before recording:** backend + frontend running, DB fresh (no reviews), browser at http://localhost:8501.

| Time | Screen | Say |
|---|---|---|
| 0:00–0:20 | Overview (empty) | "Editors hand-pick promos from every episode. This reads the screenplays and does the first pass in seconds." |
| 0:20–0:45 | Click **Find Promos** → progress bar → metric cards | "50 episodes, ~800 candidate cuts, every cut on a real screenplay timestamp, 155 distinct promos." |
| 0:45–1:25 | Promo Discovery → *For new viewers* → open #1 | Segments, hook at +2 s, cliffhanger is the last line before the cut to black, score bars, why this rank, alternative cuts, validation tab. |
| 1:25–1:45 | *Re-targeting / spoilers* tab | "Promos that reveal twists, like the Duke reveal, are kept away from cold audiences." |
| 1:45–2:05 | Approve #1 ("great opener"), reject one ("spoils the twist") → Editor Review metrics | "Decisions persist in SQLite and survive re-runs." |
| 2:05–2:25 | Spoilers & Secrets, Content Safety | "AI-generated, so an editor verifies each one. Here's a false positive the tool made." |
| 2:25–2:45 | Agent Execution Trace | "One orchestrator, five agents, 213 tasks, retries and checkpoints; one escalation shown." |
| 2:45–3:00 | Reports & Exports + Settings | "Three downloads. The model is one setting: mock offline, or Groq/Gemini. Main limit: rules find intense moments, not story-defining ones; the reference check shows it." |
