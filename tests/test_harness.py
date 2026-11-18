import pytest
from pydantic import BaseModel

from backend.harness.checkpoint import CheckpointStore
from backend.harness.executor import Executor
from backend.harness.retry_manager import RetryManager
from backend.harness.state import RunState, RunStatus, Task, TaskStatus
from backend.harness.tool_registry import ToolError, ToolRegistry
from backend.harness.tracing import Tracer


class In(BaseModel):
    x: int


class Out(BaseModel):
    y: int


@pytest.fixture
def reg():
    r = ToolRegistry()

    @r.register("double", "double x", In, Out)
    def double(ctx, inp):
        return {"y": inp.x * 2}

    @r.register("broken_out", "returns bad output", In, Out)
    def broken(ctx, inp):
        return {"nope": 1}

    @r.register("boom", "raises", In, Out)
    def boom(ctx, inp):
        raise ValueError("kaboom")
    return r


def test_tool_registry_schemas_and_errors(reg):
    assert reg.call("double", {"x": 3}, None).y == 6
    with pytest.raises(ToolError) as e:
        reg.call("double", {"x": "not int"}, None)
    assert not e.value.retryable
    with pytest.raises(ToolError):
        reg.call("broken_out", {"x": 1}, None)
    with pytest.raises(ToolError) as e:
        reg.call("boom", {"x": 1}, None)
    assert e.value.retryable and "kaboom" in str(e.value)
    with pytest.raises(ToolError):
        reg.call("missing", {}, None)
    assert {t["name"] for t in reg.describe()} == {"double", "broken_out", "boom"}
    with pytest.raises(ValueError):
        reg.register("double", "dup", In, Out)(lambda c, i: None)


def test_real_registry_has_required_tools():
    from backend.tools.output_tools import build_registry
    names = set(build_registry().names())
    for t in ("list_episode_files", "parse_episode", "get_episode_context", "get_character_history",
              "search_dramatic_moments", "find_hook_candidates", "find_cliffhanger_candidates",
              "generate_promo_candidates", "validate_promo", "calculate_promo_score", "rank_promos", "save_results"):
        assert t in names


def test_retry_limit():
    calls = []
    rm = RetryManager(max_retries=2, backoff_s=0, sleep=lambda s: None)

    def always_fail(a):
        calls.append(a)
        raise RuntimeError("x")
    with pytest.raises(RuntimeError) as e:
        rm.run(always_fail)
    assert calls == [1, 2, 3] and e.value.attempts == 3
    out, attempts = rm.run(lambda a: "ok" if a == 2 else (_ for _ in ()).throw(RuntimeError()))
    assert out == "ok" and attempts == 2


def test_no_retry_on_non_retryable():
    calls = []
    rm = RetryManager(max_retries=5, backoff_s=0, sleep=lambda s: None)

    def bad_input(a):
        calls.append(a)
        raise ToolError("t", "bad input", retryable=False)
    with pytest.raises(ToolError):
        rm.run(bad_input)
    assert calls == [1]


class FlakyAgent:
    """Fails the first `fail_times` calls of task 'b'."""
    def __init__(self, fail_times):
        self.fail_times, self.calls = fail_times, []

    def handle(self, task, ctx, tracer):
        self.calls.append(task.task_id)
        if task.task_id == "b" and self.fail_times > 0:
            self.fail_times -= 1
            raise RuntimeError("transient")
        return {"done": task.task_id}


def _state(tmp_path, critical=True):
    tasks = [Task(task_id="a", stage="1", agent="ag", tool="t"),
             Task(task_id="b", stage="1", agent="ag", tool="t", depends_on=["a"], max_retries=1, critical=critical),
             Task(task_id="c", stage="2", agent="ag", tool="t", depends_on=["b"])]
    return RunState(run_id="r1", objective="test", tasks=tasks), CheckpointStore(tmp_path)


def test_agent_state_and_checkpoint_resume(tmp_path):
    st, store = _state(tmp_path)
    agent = FlakyAgent(fail_times=5)
    tracer = Tracer("r1", tmp_path / "trace.json")
    ex = Executor(st, {"ag": agent}, tracer, store, RetryManager(1, 0, sleep=lambda s: None))
    st = ex.run(None)
    assert st.status == RunStatus.FAILED
    assert st.task("a").status == TaskStatus.COMPLETED and st.task("b").status == TaskStatus.FAILED
    assert st.task("b").attempts == 2                         # 1 try + 1 retry
    saved = store.load_state("r1")
    assert saved.task("a").status == TaskStatus.COMPLETED        # checkpoint on disk
    # resume: only b and c run again
    for t in saved.tasks:
        if t.status == TaskStatus.FAILED:
            t.status = TaskStatus.PENDING
    agent2 = FlakyAgent(fail_times=0)
    st2 = Executor(saved, {"ag": agent2}, tracer, store, RetryManager(1, 0, sleep=lambda s: None)).run(None)
    assert st2.status == RunStatus.COMPLETED and agent2.calls == ["b", "c"]
    assert st2.counts()["COMPLETED"] == 3 and st2.progress == 1.0


def test_non_critical_failure_escalates(tmp_path):
    st, store = _state(tmp_path, critical=False)
    st.tasks[2].critical = False
    ex = Executor(st, {"ag": FlakyAgent(fail_times=9)}, Tracer("r1"), store, RetryManager(0, 0, sleep=lambda s: None))
    st = ex.run(None)
    assert st.status == RunStatus.COMPLETED
    assert st.task("b").status == TaskStatus.NEEDS_REVIEW and st.escalations
    # an escalated task does not block downstream work (one bad episode must not stop the other 49)
    assert st.task("c").status == TaskStatus.COMPLETED


def test_tracing_records_and_flushes(tmp_path):
    seen = []
    tr = Tracer("r9", tmp_path / "t.json", sink=seen.append)
    tr.log(agent="a", action="start", status="RUNNING", detail="x" * 1000)
    tr.flush()
    assert len(seen) == 1 and len(seen[0]["detail"]) == 300 and (tmp_path / "t.json").exists()


def test_agent_tool_permissions():
    from backend.agents.agents import ValidationAgent
    from backend.tools.output_tools import build_registry
    ag = ValidationAgent(build_registry())
    with pytest.raises(PermissionError):
        ag.call_tool("save_results", {}, None, Tracer("x"))


def test_interrupted_run_is_unlocked_on_restart(data_dir):
    """A run left RUNNING by a crashed/restarted backend must not block the UI forever."""
    from backend.agents.orchestrator import Orchestrator
    o = Orchestrator()
    st = o.create_run()
    st.status = RunStatus.RUNNING
    st.tasks[0].status = TaskStatus.COMPLETED
    st.tasks[1].status = TaskStatus.RUNNING
    o.store.save_state(st)
    o.db.upsert_run(st)
    o2 = Orchestrator()                                   # simulates the backend restarting
    after = o2.store.load_state(st.run_id)
    assert after.status == RunStatus.FAILED and "interrupted" in after.errors[-1]["error"]
    assert after.tasks[1].status == TaskStatus.PENDING and after.tasks[0].status == TaskStatus.COMPLETED
    assert o2.db.get_run(st.run_id)["status"] == "FAILED"


def test_validation_task_is_not_escalated(data_dir):
    """Regression: a count field named needs_review used to make the executor escalate the validate task."""
    from backend.agents.orchestrator import Orchestrator
    o = Orchestrator()
    st = o.execute(o.create_run().run_id)
    assert st.status == RunStatus.COMPLETED
    assert st.task("validate").status == TaskStatus.COMPLETED
    assert "needs_review_count" in st.task("validate").output
