from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from .deps import get_db, get_orchestrator, run_info
from .schemas import RunInfo, StartRequest

router = APIRouter(prefix="/api/process", tags=["processing"])


@router.post("/start", response_model=RunInfo, status_code=202)
def start(req: StartRequest, orch=Depends(get_orchestrator), db=Depends(get_db)):
    opts = {k: v for k, v in req.model_dump().items() if v is not None and k != "episodes"}
    if req.weights:
        bad = set(req.weights) - {"hook", "cliffhanger", "standalone", "emotion", "coherence"}
        if bad or any(w < 0 for w in req.weights.values()) or sum(req.weights.values()) <= 0:
            raise HTTPException(422, "weights must be non-negative values for hook/cliffhanger/standalone/emotion/coherence")
    provs = list(dict.fromkeys(req.providers or ([req.provider] if req.provider else [])))
    if "mock" in provs and len(provs) > 1:
        raise HTTPException(422, "mock (offline) can't be combined with real LLMs; pick mock alone or real LLMs")
    import os
    missing = [p for p in provs if p not in ("mock", "ollama")
               and not (os.getenv("LLM_API_KEY") or os.getenv(f"{p.upper()}_API_KEY"))]
    if missing:
        raise HTTPException(422, f"no API key saved for: {', '.join(missing)} (add it in Settings)")
    if provs:
        opts["providers"] = provs
    try:
        st = orch.start_async(req.episodes, opts)
    except RuntimeError as e:
        raise HTTPException(409, str(e))
    except KeyError:
        raise HTTPException(404, f"unknown show '{req.show}'")
    except FileNotFoundError as e:
        raise HTTPException(400, str(e))
    return run_info(db.get_run(st.run_id))


@router.get("/status/{run_id}", response_model=RunInfo)
def status(run_id: str, db=Depends(get_db)):
    d = db.get_run(run_id)
    if not d:
        raise HTTPException(404, "run not found")
    return run_info(d)


@router.get("/runs", response_model=list[RunInfo])
def runs(limit: int = 20, db=Depends(get_db)):
    return [run_info(r) for r in db.list_runs(min(max(limit, 1), 100))]


@router.get("/latest", response_model=RunInfo | None)
def latest(db=Depends(get_db)):
    return run_info(db.latest_run())


@router.post("/resume/{run_id}", response_model=RunInfo, status_code=202)
def resume(run_id: str, orch=Depends(get_orchestrator), db=Depends(get_db)):
    try:
        orch.resume_async(run_id)
    except KeyError:
        raise HTTPException(404, "run not found")
    except (ValueError, RuntimeError) as e:
        raise HTTPException(409, str(e))
    return run_info(db.get_run(run_id))
