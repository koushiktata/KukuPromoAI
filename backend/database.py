"""SQLite persistence. Promo / secret / flag ids are stable hashes of their content, so editor
decisions survive restarts AND re-runs of the pipeline."""
from __future__ import annotations

import json
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (run_id TEXT PRIMARY KEY, status TEXT, stage TEXT, progress REAL, objective TEXT,
  config TEXT, metrics TEXT, counts TEXT, errors TEXT, created_at TEXT, updated_at TEXT, finished_at TEXT);
CREATE TABLE IF NOT EXISTS episodes (episode INTEGER PRIMARY KEY, file_name TEXT, sha1 TEXT, duration REAL,
  scenes INTEGER, events INTEGER, dialogue INTEGER, logline TEXT, issues TEXT, run_id TEXT);
CREATE TABLE IF NOT EXISTS candidates (candidate_id TEXT, run_id TEXT, data TEXT, PRIMARY KEY (candidate_id, run_id));
CREATE TABLE IF NOT EXISTS promos (promo_id TEXT PRIMARY KEY, run_id TEXT, rank INTEGER, status TEXT, overall REAL,
  new_viewer INTEGER, retarget INTEGER, first_episode INTEGER, duration REAL, data TEXT);
CREATE TABLE IF NOT EXISTS reviews (promo_id TEXT PRIMARY KEY, decision TEXT, reason TEXT, reviewer TEXT, updated_at TEXT);
CREATE TABLE IF NOT EXISTS review_history (id INTEGER PRIMARY KEY AUTOINCREMENT, promo_id TEXT, decision TEXT,
  reason TEXT, reviewer TEXT, at TEXT);
CREATE TABLE IF NOT EXISTS secrets (secret_id TEXT PRIMARY KEY, run_id TEXT, data TEXT);
CREATE TABLE IF NOT EXISTS secret_reviews (secret_id TEXT PRIMARY KEY, status TEXT, note TEXT, reviewer TEXT, updated_at TEXT);
CREATE TABLE IF NOT EXISTS flags (flag_id TEXT PRIMARY KEY, run_id TEXT, data TEXT);
CREATE TABLE IF NOT EXISTS flag_reviews (flag_id TEXT PRIMARY KEY, status TEXT, note TEXT, reviewer TEXT, updated_at TEXT);
CREATE TABLE IF NOT EXISTS traces (run_id TEXT, seq INTEGER, data TEXT, PRIMARY KEY (run_id, seq));
"""

DECISIONS = ("not_reviewed", "approved", "rejected")
VERIFY = ("unreviewed", "verified", "incorrect", "needs_review")


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Database:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        with self.conn() as c:
            c.execute("PRAGMA journal_mode=WAL")
            c.executescript(SCHEMA)

    @contextmanager
    def conn(self):
        c = sqlite3.connect(self.path, timeout=30, check_same_thread=False)
        c.row_factory = sqlite3.Row
        try:
            yield c
            c.commit()
        finally:
            c.close()

    # ---------- runs ----------
    def upsert_run(self, st) -> None:
        with self._lock, self.conn() as c:
            c.execute("""INSERT INTO runs VALUES (?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(run_id) DO UPDATE SET
              status=excluded.status, stage=excluded.stage, progress=excluded.progress, metrics=excluded.metrics,
              counts=excluded.counts, errors=excluded.errors, updated_at=excluded.updated_at,
              finished_at=excluded.finished_at""",
                      (st.run_id, st.status.value, st.stage, st.progress, st.objective, json.dumps(st.config),
                       json.dumps(st.metrics), json.dumps(st.counts()), json.dumps(st.errors[-20:]),
                       st.created_at, st.updated_at, st.finished_at))

    def get_run(self, run_id: str) -> dict | None:
        with self.conn() as c:
            r = c.execute("SELECT * FROM runs WHERE run_id=?", (run_id,)).fetchone()
        return self._run(r) if r else None

    def latest_run(self, completed_only: bool = False) -> dict | None:
        # timestamps have 1-second precision, so break ties by insertion order (rowid)
        q = ("SELECT * FROM runs WHERE status='COMPLETED' ORDER BY finished_at DESC, rowid DESC LIMIT 1" if completed_only
             else "SELECT * FROM runs ORDER BY created_at DESC, rowid DESC LIMIT 1")
        with self.conn() as c:
            r = c.execute(q).fetchone()
        return self._run(r) if r else None

    def list_runs(self, limit: int = 20) -> list[dict]:
        with self.conn() as c:
            return [self._run(r) for r in c.execute("SELECT * FROM runs ORDER BY created_at DESC, rowid DESC LIMIT ?",
                                                    (limit,))]

    @staticmethod
    def _run(r) -> dict:
        d = dict(r)
        for k in ("config", "metrics", "counts", "errors"):
            d[k] = json.loads(d[k] or "{}")
        return d

    # ---------- results ----------
    def replace_results(self, run_id: str, episodes: list[dict], candidates: list[dict], promos: list[dict],
                        secrets: list[dict], flags: list[dict]) -> None:
        with self._lock, self.conn() as c:
            c.execute("DELETE FROM episodes")
            c.executemany("INSERT INTO episodes VALUES (?,?,?,?,?,?,?,?,?,?)",
                          [(e["episode"], e["file_name"], e["sha1"], e["duration"], e["scenes"], e["events"],
                            e["dialogue"], e["logline"], json.dumps(e["issues"]), run_id) for e in episodes])
            c.execute("DELETE FROM candidates WHERE run_id=?", (run_id,))
            c.executemany("INSERT INTO candidates VALUES (?,?,?)",
                          [(p["promo_id"], run_id, json.dumps(p)) for p in candidates])
            c.execute("DELETE FROM promos")
            c.executemany("INSERT INTO promos VALUES (?,?,?,?,?,?,?,?,?,?)",
                          [(p["promo_id"], run_id, p.get("rank"), p["validation"]["status"], p["scores"]["overall"],
                            int(p["category"]["new_viewer"]), int(p["category"]["retarget"]),
                            p["segments"][0]["episode"], p["duration"], json.dumps(p)) for p in promos])
            c.execute("DELETE FROM secrets")
            c.executemany("INSERT INTO secrets VALUES (?,?,?)", [(s["secret_id"], run_id, json.dumps(s)) for s in secrets])
            c.execute("DELETE FROM flags")
            c.executemany("INSERT INTO flags VALUES (?,?,?)", [(f["flag_id"], run_id, json.dumps(f)) for f in flags])

    def promos(self) -> list[dict]:
        with self.conn() as c:
            rows = c.execute("""SELECT p.data, r.decision, r.reason, r.reviewer, r.updated_at FROM promos p
                                LEFT JOIN reviews r ON r.promo_id = p.promo_id
                                ORDER BY CASE WHEN p.rank IS NULL THEN 1 ELSE 0 END, p.rank, p.overall DESC""").fetchall()
        out = []
        for r in rows:
            d = json.loads(r["data"])
            d["review"] = {"decision": r["decision"] or "not_reviewed", "reason": r["reason"] or "",
                           "reviewer": r["reviewer"] or "", "updated_at": r["updated_at"] or ""}
            out.append(d)
        return out

    def promo(self, promo_id: str) -> dict | None:
        return next((p for p in self.promos() if p["promo_id"] == promo_id), None)

    def candidate_count(self, run_id: str) -> int:
        with self.conn() as c:
            return c.execute("SELECT COUNT(*) FROM candidates WHERE run_id=?", (run_id,)).fetchone()[0]

    def episodes(self) -> list[dict]:
        with self.conn() as c:
            rows = [dict(r) for r in c.execute("SELECT * FROM episodes ORDER BY episode")]
        for r in rows:
            r["issues"] = json.loads(r["issues"] or "[]")
        return rows

    # ---------- reviews ----------
    def set_review(self, promo_id: str, decision: str, reason: str = "", reviewer: str = "") -> dict:
        if decision not in DECISIONS:
            raise ValueError(f"decision must be one of {DECISIONS}")
        at = utcnow()
        with self._lock, self.conn() as c:
            c.execute("""INSERT INTO reviews VALUES (?,?,?,?,?) ON CONFLICT(promo_id) DO UPDATE SET
                         decision=excluded.decision, reason=excluded.reason, reviewer=excluded.reviewer,
                         updated_at=excluded.updated_at""", (promo_id, decision, reason, reviewer, at))
            c.execute("INSERT INTO review_history (promo_id, decision, reason, reviewer, at) VALUES (?,?,?,?,?)",
                      (promo_id, decision, reason, reviewer, at))
        return {"promo_id": promo_id, "decision": decision, "reason": reason, "reviewer": reviewer, "updated_at": at}

    def review_history(self, promo_id: str) -> list[dict]:
        with self.conn() as c:
            return [dict(r) for r in c.execute("SELECT decision, reason, reviewer, at FROM review_history "
                                               "WHERE promo_id=? ORDER BY id DESC", (promo_id,))]

    def review_stats(self) -> dict:
        ranked = [p for p in self.promos() if p.get("rank")]
        dec = [p["review"]["decision"] for p in ranked]
        approved, rejected = dec.count("approved"), dec.count("rejected")
        reviewed = approved + rejected
        return {"total": len(ranked), "reviewed": reviewed, "approved": approved, "rejected": rejected,
                "not_reviewed": len(ranked) - reviewed,
                "approval_rate": round(approved / reviewed, 3) if reviewed else None}

    # ---------- secrets / flags ----------
    def _items(self, table: str, review_table: str, key: str) -> list[dict]:
        with self.conn() as c:
            rows = c.execute(f"""SELECT t.data, r.status, r.note, r.reviewer, r.updated_at FROM {table} t
                                 LEFT JOIN {review_table} r ON r.{key} = t.{key}""").fetchall()
        out = []
        for r in rows:
            d = json.loads(r["data"])
            d["review"] = {"status": r["status"] or "unreviewed", "note": r["note"] or "",
                           "reviewer": r["reviewer"] or "", "updated_at": r["updated_at"] or ""}
            out.append(d)
        return out

    def secrets(self) -> list[dict]:
        return sorted(self._items("secrets", "secret_reviews", "secret_id"), key=lambda s: s["reveal_episode"])

    def flags(self) -> list[dict]:
        return sorted(self._items("flags", "flag_reviews", "flag_id"), key=lambda f: (f["episode"], f["start"]))

    def _set_verify(self, table: str, key: str, item_id: str, status: str, note: str, reviewer: str) -> dict:
        if status not in VERIFY:
            raise ValueError(f"status must be one of {VERIFY}")
        at = utcnow()
        with self._lock, self.conn() as c:
            c.execute(f"""INSERT INTO {table} VALUES (?,?,?,?,?) ON CONFLICT({key}) DO UPDATE SET status=excluded.status,
                          note=excluded.note, reviewer=excluded.reviewer, updated_at=excluded.updated_at""",
                      (item_id, status, note, reviewer, at))
        return {key: item_id, "status": status, "note": note, "updated_at": at}

    def set_secret_review(self, sid, status, note="", reviewer=""):
        return self._set_verify("secret_reviews", "secret_id", sid, status, note, reviewer)

    def set_flag_review(self, fid, status, note="", reviewer=""):
        return self._set_verify("flag_reviews", "flag_id", fid, status, note, reviewer)

    # ---------- traces ----------
    def add_trace(self, ev: dict) -> None:
        with self._lock, self.conn() as c:
            c.execute("INSERT OR REPLACE INTO traces VALUES (?,?,?)", (ev["run_id"], ev["seq"], json.dumps(ev)))

    def traces(self, run_id: str, limit: int = 5000) -> list[dict]:
        with self.conn() as c:
            return [json.loads(r[0]) for r in c.execute(
                "SELECT data FROM traces WHERE run_id=? ORDER BY seq LIMIT ?", (run_id, limit))]
