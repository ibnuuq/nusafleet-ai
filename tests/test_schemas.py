import pytest
from pydantic import ValidationError

from src.models.schemas import Agent, Evidence, EvidenceKind, RunState, Task, TaskResult, TaskStatus, Tool


def test_tool_defaults_to_read_only():
    tool = Tool(name="query", description="d")
    assert tool.is_read_only is True


def test_tool_missing_required_field_rejected():
    with pytest.raises(ValidationError):
        Tool(description="missing name")


def test_agent_allowed_tools_defaults_empty():
    agent = Agent(agent_id="a1", name="A", role="r", system_prompt="p")
    assert agent.allowed_tools == []


def test_task_defaults_pending():
    task = Task(task_id="t1", description="d")
    assert task.status == TaskStatus.PENDING
    assert task.depends_on == []


def test_task_result_invalid_status_rejected():
    with pytest.raises(ValidationError):
        TaskResult(task_id="t1", status="not-a-status")


def test_evidence_requires_known_kind():
    with pytest.raises(ValidationError):
        Evidence(evidence_id="e1", kind="not-a-kind", content="x", source="s")

    ev = Evidence(evidence_id="e1", kind=EvidenceKind.TABLE, content=[{"a": 1}], source="sql:...")
    assert ev.kind == EvidenceKind.TABLE


def test_run_state_defaults():
    run = RunState(run_id="r1", question="why?")
    assert run.status.value == "pending"
    assert run.iteration == 0
    assert run.tasks == []
    assert run.results == []
