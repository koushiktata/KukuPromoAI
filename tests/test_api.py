"""End-to-end: run the real agentic pipeline on synthetic screenplays through the API."""
import io
import time

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def client(data_dir):
    from backend.main import app
    c = TestClient(app)
    r = c.post("/api/process/start", json={})
    assert r.status_code == 202, r.text
    rid = r.json()["run_id"]
    for _ in range(300):
        st = c.get(f"/api/process/status/{rid}").json()
        if st["status"] in ("COMPLETED", "FAILED"):
            break
        time.sleep(0.1)
    assert st["status"] == "COMPLETED", st
    c.run_id = rid
    return c


def test_health(client):
    h = client.get("/api/health").json()
    assert h["status"] == "ok" and h["data_files"] == 3 and h["api_key_set"] in (True, False)


def test_episodes(client):
    d = client.get("/api/episodes").json()
    assert d["processed"] == 3 and d["missing"] == []
    assert client.get("/api/episodes/1").status_code == 200
    assert client.get("/api/episodes/77").status_code == 404


def test_second_run_conflict_or_ok(client):
    r = client.post("/api/process/start", json={"provider": "nope"})
    assert r.status_code == 422


def test_promos_and_filters(client):
    d = client.get("/api/promos").json()
    assert d["count"] > 0
    assert all(p["rank"] for p in d["promos"])
    nv = client.get("/api/promos", params={"category": "new_viewer"}).json()
    assert nv["count"] == d["category_counts"]["new_viewer"]
    hi = client.get("/api/promos", params={"min_score": 4.9}).json()
    assert all(p["scores"]["overall"] >= 4.9 for p in hi["promos"])
    assert client.get("/api/promos", params={"category": "bogus"}).status_code == 422


def test_promo_detail_validate_and_404(client):
    pid = client.get("/api/promos").json()["promos"][0]["promo_id"]
    d = client.get(f"/api/promos/{pid}", params={"include_transcript": True}).json()
    assert d["transcript"] and d["segments"]
    v = client.post(f"/api/promos/{pid}/validate").json()
    assert v["consistent"]
    assert client.get("/api/promos/Pnope").status_code == 404


def test_review_persistence_stats_and_exports(client):
    from backend.config import settings
    from backend.database import Database
    promos = client.get("/api/promos").json()["promos"]
    a, b = promos[0]["promo_id"], promos[1]["promo_id"]
    # nothing approved -> approved export has zero rows
    r = client.get("/api/reports/approved")
    assert r.headers["x-row-count"] == "0" and len(r.text.strip().splitlines()) == 1
    assert client.post(f"/api/promos/{a}/review", json={"decision": "approved", "reason": "great opener"}).status_code == 200
    s = client.post(f"/api/promos/{b}/review", json={"decision": "rejected", "reason": "spoils the twist"}).json()["stats"]
    assert s["reviewed"] == 2 and s["approved"] == 1 and s["rejected"] == 1 and s["approval_rate"] == 0.5
    assert client.post(f"/api/promos/{a}/review", json={"decision": "maybe"}).status_code == 422
    # persistence: a brand-new DB connection sees it
    assert Database(settings.db_path).promo(a)["review"]["decision"] == "approved"
    hist = client.get(f"/api/promos/{a}").json()["review_history"]
    assert hist[0]["decision"] == "approved"
    assert client.get("/api/reports/approved").headers["x-row-count"] == "1"
    allcsv = client.get("/api/reports/all-decisions").text
    assert "great opener" in allcsv and "spoils the twist" in allcsv and "Not reviewed" in allcsv
    md = client.get("/api/reports/full").text
    assert "Editor decision:** Approved — great opener" in md and "secrets" in md.lower()
    # back to not reviewed: not counted as approve/reject
    s = client.post(f"/api/promos/{b}/review", json={"decision": "not_reviewed"}).json()["stats"]
    assert s["reviewed"] == 1 and s["rejected"] == 0


def test_reviews_survive_rerun(client):
    pid = client.get("/api/promos").json()["promos"][0]["promo_id"]
    client.post(f"/api/promos/{pid}/review", json={"decision": "approved"})
    from backend.api.deps import get_orchestrator
    st = get_orchestrator().execute(get_orchestrator().create_run().run_id)
    assert st.status.value == "COMPLETED"
    p = client.get(f"/api/promos/{pid}")
    assert p.status_code == 200 and p.json()["review"]["decision"] == "approved"


def test_secrets_and_flags_review(client):
    s = client.get("/api/secrets").json()
    assert s["ai_generated"] and s["count"] > 0
    sid = s["secrets"][0]["secret_id"]
    assert client.post(f"/api/secrets/{sid}/review", json={"status": "verified"}).status_code == 200
    assert client.get("/api/secrets").json()["secrets"][0]["review"]["status"] in ("verified", "unreviewed")
    assert client.post("/api/secrets/nope/review", json={"status": "verified"}).status_code == 404
    f = client.get("/api/content-flags").json()
    assert f["count"] > 0 and "not legal" in f["disclaimer"]
    fid = f["flags"][0]["flag_id"]
    assert client.post(f"/api/content-flags/{fid}/review", json={"status": "incorrect"}).status_code == 200
    assert client.post(f"/api/content-flags/{fid}/review", json={"status": "bogus"}).status_code == 422


def test_summary_trace_status_evaluation(client):
    s = client.get("/api/reports/summary").json()
    assert s["episodes"] == 3 and s["ranked"] > 0 and s["candidates"] >= s["ranked"]
    t = client.get(f"/api/agents/trace/{client.run_id}").json()["events"]
    assert any(e["action"] == "tool_call" for e in t)
    a = client.get(f"/api/agents/status/{client.run_id}").json()
    assert {x["agent"] for x in a["agents"]} >= {"screenplay_agent", "promo_discovery_agent", "validation_agent",
                                                  "scoring_agent", "quality_reviewer_agent"}
    ev = client.get("/api/reports/evaluation").json()
    assert ev["hook_within_3s_rate"] == 1.0
    assert client.get("/api/agents/trace/nope").status_code == 404


def test_output_files_written(client):
    from backend.config import settings
    for name in ("parsed_screenplays.json", "candidate_moments.json", "validated_promos.json", "ranked_promos.json",
                 "ranked_promos.csv", "evaluation_results.csv", "agent_execution_trace.json", "agent_run_summary.json",
                 "processing_report.json", "ranked.md", "data_inventory.json", "screenplay_format_report.md"):
        assert (settings.output_dir / name).exists(), name
    assert client.get("/api/reports/file/ranked_promos.json").status_code == 200
    assert client.get("/api/reports/file/../../etc/passwd").status_code == 404


def test_upload_validation(client, data_dir):
    from conftest import make_episode
    bad = client.post("/api/episodes/upload", files=[("files", ("evil.exe", b"x", "application/octet-stream"))])
    assert bad.status_code == 422
    junk = client.post("/api/episodes/upload", files=[("files", ("notes.txt", b"hello", "text/plain"))])
    assert junk.status_code == 422
    ok = client.post("/api/episodes/upload", files=[("files", ("episode-004-Episode 9004.txt",
                                                               io.BytesIO(make_episode(4).encode()), "text/plain"))])
    assert ok.status_code == 201 and ok.json()["saved"][0]["episode"] == 4
    (data_dir / "episode-004-Episode 9004.txt").unlink()          # keep the shared fixture at 3 episodes


def test_api_keys_are_write_only(client):
    from backend.config import ENV_FILE
    fake = "gsk_test_ABCDEFGHIJKLMNOP1234"
    assert client.put("/api/settings/keys/groq", json={"api_key": "has spaces in it 1234567"}).status_code == 422
    assert client.put("/api/settings/keys/nope", json={"api_key": fake}).status_code == 404
    r = client.put("/api/settings/keys/groq", json={"api_key": fake})
    assert r.status_code == 200 and r.json()["set"] and r.json()["hint"] == "••••1234"
    assert fake not in r.text
    listing = client.get("/api/settings/keys")
    assert fake not in listing.text
    assert next(p for p in listing.json()["providers"] if p["provider"] == "groq")["set"]
    assert f"GROQ_API_KEY={fake}" in ENV_FILE.read_text()
    assert "groq" in client.get("/api/health").json()["keys_present"]
    gone = client.delete("/api/settings/keys/groq").json()
    assert not gone["set"] and "GROQ_API_KEY" not in ENV_FILE.read_text()
    t = client.post("/api/settings/keys/groq/test", json={}).json()       # no key -> fails before any network call
    assert t["ok"] is False and "no API key" in t["error"]


def test_start_validates_llm_choices(client):
    assert client.post("/api/process/start", json={"providers": ["mock", "groq"]}).status_code == 422
    r = client.post("/api/process/start", json={"providers": ["groq", "gemini"]})
    assert r.status_code == 422 and "groq" in r.text           # no keys saved in tests
    assert client.post("/api/process/start", json={"providers": ["bogus"]}).status_code == 422
    assert client.post("/api/process/start", json={"show": "no-such-show"}).status_code == 404


def test_upload_show_and_get_timestamps(client):
    """Main flow: upload several episode files as a new show -> run -> ranked promo timestamps for THAT show."""
    from conftest import make_episode
    files = [("files", (f"episode-00{n}-Ep.txt", make_episode(n).replace("Mara", "Nina").replace("MARA", "NINA").encode(), "text/plain"))
             for n in (1, 2)] + [("files", ("readme.txt", b"not a screenplay", "text/plain"))]
    r = client.post("/api/shows", data={"name": "Nina's Revenge"}, files=files)
    assert r.status_code == 201, r.text
    body = r.json()
    sid = body["show"]["show_id"]
    assert sid == "nina-s-revenge" and len(body["saved"]) == 2 and body["rejected"][0]["file"] == "readme.txt"
    assert any(s["show_id"] == sid and s["files"] == 2 for s in client.get("/api/shows").json()["shows"])
    run = client.post("/api/process/start", json={"show": sid}).json()
    for _ in range(300):
        st = client.get(f"/api/process/status/{run['run_id']}").json()
        if st["status"] in ("COMPLETED", "FAILED"):
            break
        time.sleep(0.1)
    assert st["status"] == "COMPLETED", st
    s = client.get("/api/reports/summary").json()
    assert s["show_name"] == "Nina's Revenge" and s["episodes"] == 2 and s["judges"] == ["mock"]
    promos = client.get("/api/promos").json()["promos"]
    assert promos and all(seg["episode"] in (1, 2) for p in promos for seg in p["segments"])
    p = promos[0]
    assert p["segments"][0]["start_ts"] and p["segments"][0]["end_ts"] and 20 <= p["duration"] <= 60
    tr = client.get(f"/api/promos/{p['promo_id']}", params={"include_transcript": True}).json()["transcript"]
    assert any("NINA" in line["who"] or "Nina" in line["text"] for seg in tr for line in seg["lines"])     # transcript comes from the new show
    assert client.post("/api/shows", data={"name": "x"},
                       files=[("files", ("bad.txt", b"hello", "text/plain"))]).status_code == 422


def test_keys_locked_on_hosted_deployments(client, monkeypatch):
    monkeypatch.setenv("KUKU_LOCK_KEYS", "1")
    assert client.put("/api/settings/keys/groq", json={"api_key": "gsk_test_ABCDEFGHIJKLMNOP1234"}).status_code == 403
    assert client.delete("/api/settings/keys/groq").status_code == 403
    d = client.get("/api/settings/keys").json()
    assert d["locked"] and all("••••" not in (p.get("hint") or "") for p in d["providers"])
    assert client.get("/api/health").json()["keys_locked"] is True
