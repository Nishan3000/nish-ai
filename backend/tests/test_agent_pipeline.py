"""Tests for the task state machine, planner agent, and agent API.

Ollama is mocked with respx throughout. Run with:
    pytest tests/test_agent_pipeline.py
"""

import json
from pathlib import Path

import httpx
import pytest
import respx
from fastapi.testclient import TestClient

from app.agents.models import AgentTask, Plan, TaskState
from app.agents.planner import PlannerAgent, PlanningError, _extract_json
from app.agents.state_machine import (
    ALLOWED_TRANSITIONS,
    IllegalTransitionError,
    transition,
)
from app.core.audit import AuditLogger
from app.core.config import Settings, get_settings
from app.services.ollama import OllamaService
from app.tools.path_guard import PathGuard
from app.tools.permissions import Capability, build_default_registry
from app.tools.repo_reader import RepoReader

READ = frozenset({Capability.READ_REPO})

VALID_PLAN = {
    "goal": "Add a subtract function to the calculator",
    "assumptions": ["Python project with pytest"],
    "risks": ["Existing callers may rely on current API"],
    "steps": [
        {
            "id": 1,
            "title": "Inspect calculator module",
            "kind": "inspect",
            "description": "Read src/main.py to find the calculator API.",
            "target_files": ["src/main.py"],
        },
        {
            "id": 2,
            "title": "Run tests",
            "kind": "test",
            "description": "Run pytest to confirm baseline.",
            "target_files": [],
        },
    ],
}


# ---------------------------------------------------------- state machine ---


def _audit(tmp_path: Path) -> AuditLogger:
    return AuditLogger(tmp_path / "audit.jsonl")


def test_happy_path_transitions(tmp_path: Path) -> None:
    task = AgentTask(description="do something useful")
    audit = _audit(tmp_path)
    for state in [TaskState.PLANNING, TaskState.PLANNED]:
        transition(task, state, audit)
    assert task.state is TaskState.PLANNED
    assert [record.to_state for record in task.history] == [
        TaskState.PLANNING,
        TaskState.PLANNED,
    ]


def test_cannot_jump_straight_to_merging(tmp_path: Path) -> None:
    """The critical property: MERGING is unreachable without approval."""
    task = AgentTask(description="sneaky merge attempt")
    with pytest.raises(IllegalTransitionError):
        transition(task, TaskState.MERGING, _audit(tmp_path))


def test_merging_only_reachable_from_awaiting_approval() -> None:
    sources = [
        state
        for state, targets in ALLOWED_TRANSITIONS.items()
        if TaskState.MERGING in targets
    ]
    assert sources == [TaskState.AWAITING_APPROVAL]


def test_terminal_states_have_no_exits() -> None:
    for state in (
        TaskState.COMPLETED,
        TaskState.REJECTED,
        TaskState.FAILED,
        TaskState.CANCELLED,
    ):
        assert ALLOWED_TRANSITIONS[state] == frozenset()


def test_illegal_transition_is_audited(tmp_path: Path) -> None:
    task = AgentTask(description="illegal transition check")
    audit = _audit(tmp_path)
    with pytest.raises(IllegalTransitionError):
        transition(task, TaskState.TESTING, audit)
    entries = [json.loads(line) for line in audit.path.read_text().splitlines()]
    assert entries[-1]["outcome"] == "denied"


# ----------------------------------------------------------------- planner ---


def _planner(tmp_path: Path) -> PlannerAgent:
    workspace = tmp_path / "ws"
    (workspace / "src").mkdir(parents=True)
    (workspace / "src" / "main.py").write_text("def add(a, b): return a + b\n")
    settings = Settings(agent_workspace_root=str(workspace))
    audit = AuditLogger(tmp_path / "audit.jsonl")
    reader = RepoReader(
        PathGuard(workspace),
        build_default_registry(audit),
        audit,
        max_read_bytes=10_000,
        max_tree_entries=100,
    )
    return PlannerAgent(OllamaService(settings), reader, audit, settings)


def _ollama_reply(content: str) -> httpx.Response:
    return httpx.Response(
        200, json={"message": {"role": "assistant", "content": content}}
    )


OLLAMA_CHAT = "http://localhost:11434/api/chat"


@respx.mock
@pytest.mark.asyncio
async def test_planner_parses_valid_plan(tmp_path: Path) -> None:
    respx.post(OLLAMA_CHAT).mock(return_value=_ollama_reply(json.dumps(VALID_PLAN)))
    plan = await _planner(tmp_path).plan("t1", "add a subtract function", READ)
    assert isinstance(plan, Plan)
    assert len(plan.steps) == 2
    assert plan.steps[0].kind == "inspect"


@respx.mock
@pytest.mark.asyncio
async def test_planner_strips_fences_and_thinking(tmp_path: Path) -> None:
    wrapped = (
        "<think>I should plan carefully...</think>\n"
        "```json\n" + json.dumps(VALID_PLAN) + "\n```"
    )
    respx.post(OLLAMA_CHAT).mock(return_value=_ollama_reply(wrapped))
    plan = await _planner(tmp_path).plan("t2", "add a subtract function", READ)
    assert plan.goal.startswith("Add a subtract")


@respx.mock
@pytest.mark.asyncio
async def test_planner_repairs_after_invalid_json(tmp_path: Path) -> None:
    responses = [
        _ollama_reply("Sure! Here is a plan in prose, no JSON."),
        _ollama_reply(json.dumps(VALID_PLAN)),
    ]
    route = respx.post(OLLAMA_CHAT)
    route.side_effect = responses
    plan = await _planner(tmp_path).plan("t3", "add a subtract function", READ)
    assert len(plan.steps) == 2
    assert route.call_count == 2


@respx.mock
@pytest.mark.asyncio
async def test_planner_fails_loudly_after_max_attempts(tmp_path: Path) -> None:
    respx.post(OLLAMA_CHAT).mock(return_value=_ollama_reply("not json, ever"))
    with pytest.raises(PlanningError, match="attempts"):
        await _planner(tmp_path).plan("t4", "add a subtract function", READ)


def test_extract_json_isolates_object() -> None:
    raw = 'noise before {"a": 1} noise after'
    assert json.loads(_extract_json(raw)) == {"a": 1}
    with pytest.raises(ValueError):
        _extract_json("no braces here")


# --------------------------------------------------------------- agent API ---


@pytest.fixture()
def api_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """App wired to a temp workspace and temp audit log."""
    workspace = tmp_path / "ws"
    (workspace / "src").mkdir(parents=True)
    (workspace / "src" / "main.py").write_text("print('x')\n")
    (workspace / ".env").write_text("SECRET=1\n")
    monkeypatch.setenv("AGENT_WORKSPACE_ROOT", str(workspace))
    monkeypatch.setenv("AGENT_AUDIT_LOG_PATH", str(tmp_path / "audit.jsonl"))

    get_settings.cache_clear()
    from app.api.agent import get_context

    get_context.cache_clear()
    from app.main import app

    yield TestClient(app)
    get_settings.cache_clear()
    get_context.cache_clear()


@respx.mock
def test_create_task_reaches_planned(api_client: TestClient) -> None:
    respx.post(OLLAMA_CHAT).mock(return_value=_ollama_reply(json.dumps(VALID_PLAN)))
    respx.get("http://localhost:11434/api/tags").mock(
        return_value=httpx.Response(200, json={"models": []})
    )
    response = api_client.post(
        "/api/agent/tasks", json={"description": "add a subtract function"}
    )
    assert response.status_code == 201
    body = response.json()
    assert body["state"] == "planned"
    assert len(body["plan"]["steps"]) == 2

    # Task is retrievable and history shows the full path.
    task = api_client.get(f"/api/agent/tasks/{body['id']}").json()
    assert [record["to_state"] for record in task["history"]] == [
        "planning",
        "planned",
    ]


@respx.mock
def test_create_task_failure_is_visible(api_client: TestClient) -> None:
    respx.post(OLLAMA_CHAT).mock(return_value=_ollama_reply("never json"))
    response = api_client.post(
        "/api/agent/tasks", json={"description": "doomed planning request"}
    )
    assert response.status_code == 502
    tasks = api_client.get("/api/agent/tasks").json()["tasks"]
    assert tasks[0]["state"] == "failed"
    assert "attempts" in tasks[0]["error"]


def test_repo_tree_hides_secrets(api_client: TestClient) -> None:
    body = api_client.get("/api/agent/repo/tree").json()
    paths = {entry["path"] for entry in body["entries"]}
    assert "src/main.py" in paths
    assert ".env" not in paths


def test_repo_file_denies_escape_and_secrets(api_client: TestClient) -> None:
    assert (
        api_client.get("/api/agent/repo/file", params={"path": "../x"}).status_code
        == 403
    )
    assert (
        api_client.get("/api/agent/repo/file", params={"path": ".env"}).status_code
        == 403
    )


def test_repo_file_reads_allowed_file(api_client: TestClient) -> None:
    body = api_client.get(
        "/api/agent/repo/file", params={"path": "src/main.py"}
    ).json()
    assert "print" in body["content"]


def test_audit_verify_endpoint(api_client: TestClient) -> None:
    api_client.get("/api/agent/repo/tree")  # generate at least one record
    body = api_client.get("/api/agent/audit/verify").json()
    assert body["ok"] is True
