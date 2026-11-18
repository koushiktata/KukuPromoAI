from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from .deps import get_db, get_orchestrator

router = APIRouter(prefix="/api/agents", tags=["agents"])


@router.get("/trace/{run_id}")
def trace(run_id: str, limit: int = 5000, db=Depends(get_db)):
    if not db.get_run(run_id):
        raise HTTPException(404, "run not found")
    return {"run_id": run_id, "events": db.traces(run_id, limit)}


@router.get("/status/{run_id}")
def status(run_id: str, orch=Depends(get_orchestrator)):
    st = orch.state(run_id)
    if not st:
        raise HTTPException(404, "run not found")
    agents: dict[str, dict] = {}
    for t in st.tasks:
        a = agents.setdefault(t.agent, {"agent": t.agent, "tasks": 0, "PENDING": 0, "RUNNING": 0, "COMPLETED": 0,
                                        "FAILED": 0, "NEEDS_REVIEW": 0, "retries": 0, "ms": 0})
        a["tasks"] += 1
        a[t.status.value] += 1
        a["retries"] += max(0, t.attempts - 1)
        a["ms"] += t.duration_ms
    roles = {name: ag.role for name, ag in orch.agents.items()}
    for name, a in agents.items():
        a["role"] = roles.get(name, "")
    return {"run_id": run_id, "status": st.status.value, "stage": st.stage, "progress": st.progress,
            "agents": list(agents.values()),
            "tasks": [t.model_dump(exclude={"args"}) | {"args": t.args} for t in st.tasks],
            "escalations": st.escalations, "errors": st.errors}


@router.get("/tools")
def tools(orch=Depends(get_orchestrator)):
    return {"tools": [{"name": t["name"], "description": t["description"]} for t in orch.registry.describe()]}
