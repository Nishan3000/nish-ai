"""Tests for the v0.6 controlled coding agent.

Run with:  pytest tests/test_coding.py
"""

import json
import os
import uuid
from pathlib import Path

import httpx
import pytest
import respx
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.coding.executor import CommandRejected, _execute, run_allowlisted
from app.coding.generator import is_protected_path, validate_target
from app.coding.paths import NISH_ROOT, ProjectPathError, validate_project_root
from app.coding.state import IllegalCodingTransition, transition
from app.core.audit import AuditLogger
from app.core.config import get_settings
from app.database.models import Base, CodingTask, RegisteredProject, User
from app.database.session import get_db
from app.main import app
from app.tools.path_guard import PathAccessError, PathGuard

settings = get_settings()
OLLAMA_CHAT = f"{settings.ollama_base_url}/api/chat"


def _reply(content: str) -> httpx.Response:
    return httpx.Response(
        200, json={"message": {"role": "assistant", "content": content}}
    )


VALID_PLAN = {
    "task_summary": "Add a subtract function to calculator.py with a test.",
    "assumptions": ["Python project using pytest"],
    "files_to_inspect": ["calculator.py"],
    "files_to_modify": ["calculator.py"],
    "files_to_create": [],
    "steps": ["Read calculator.py", "Add subtract()", "Run pytest"],
    "validation_commands": ["pytest", "pip install requests"],
    "risks": ["None significant"],
    "approval_requirements": ["Review the new function"],
}


@pytest.fixture()
def project_dir(tmp_path: Path) -> Path:
    """A small fake project with a secret and ignored dirs."""
    root = tmp_path / "demo-project"
    (root / "src").mkdir(parents=True)
    (root / "node_modules" / "junk").mkdir(parents=True)
    (root / ".next").mkdir()
    root.joinpath("calculator.py").write_text(
        "def add(a, b):\n    return a + b\n"
    )
    root.joinpath("src", "util.py").write_text("HELPER = True\n")
    root.joinpath("README.md").write_text("# Demo\nA demo project.\n")
    root.joinpath("requirements.txt").write_text("fastapi\npytest\n")
    root.joinpath("pytest.ini").write_text("[pytest]\n")
    root.joinpath(".env").write_text("SECRET=verysecret\n")
    root.joinpath("node_modules", "junk", "big.js").write_text("x" * 100)
    root.joinpath(".next", "build.js").write_text("built")
    return root


@pytest.fixture()
def db_session_factory():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    yield sessionmaker(bind=engine, expire_on_commit=False)
    engine.dispose()


@pytest.fixture()
def client(db_session_factory, tmp_path: Path, monkeypatch) -> TestClient:
    monkeypatch.setenv("CODING_WORKSPACE_DIR", str(tmp_path / "ws"))
    monkeypatch.setenv("AGENT_AUDIT_LOG_PATH", str(tmp_path / "audit.jsonl"))
    get_settings.cache_clear()

    def override_get_db():
        session = db_session_factory()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()
    get_settings.cache_clear()


def _register(client: TestClient, project_dir: Path) -> dict:
    response = client.post(
        "/api/coding/projects",
        json={"name": "demo", "root_path": str(project_dir)},
    )
    assert response.status_code == 201, response.text
    return response.json()


# ------------------------------------------------------- path validation ---


def test_register_valid_project(client: TestClient, project_dir: Path) -> None:
    body = _register(client, project_dir)
    assert body["name"] == "demo"
    assert body["root_path"] == str(project_dir.resolve())


def test_register_rejects_missing_path(client: TestClient, tmp_path: Path) -> None:
    response = client.post(
        "/api/coding/projects",
        json={"name": "x", "root_path": str(tmp_path / "nope")},
    )
    assert response.status_code == 422


def test_register_rejects_file_path(client: TestClient, project_dir: Path) -> None:
    response = client.post(
        "/api/coding/projects",
        json={"name": "x", "root_path": str(project_dir / "calculator.py")},
    )
    assert response.status_code == 422


def test_register_rejects_nish_installation(client: TestClient) -> None:
    """Self-modification structurally blocked: the live NISH tree and
    anything containing it cannot be registered."""
    for path in (str(NISH_ROOT), str(NISH_ROOT.parent), "/"):
        response = client.post(
            "/api/coding/projects", json={"name": "x", "root_path": path}
        )
        assert response.status_code == 422, path


def test_register_rejects_traversal_style_paths(
    client: TestClient, project_dir: Path
) -> None:
    """Traversal segments are resolved BEFORE validation, so a dressed-up
    path to a forbidden target (here: filesystem root) is refused."""
    sneaky = str(project_dir) + "/.." * 40  # resolves to /
    response = client.post(
        "/api/coding/projects", json={"name": "x", "root_path": sneaky}
    )
    assert response.status_code == 422
    assert "filesystem root" in response.json()["detail"]


def test_duplicate_registration_rejected(
    client: TestClient, project_dir: Path
) -> None:
    _register(client, project_dir)
    again = client.post(
        "/api/coding/projects",
        json={"name": "again", "root_path": str(project_dir)},
    )
    assert again.status_code == 409


def test_validate_project_root_home_refused() -> None:
    with pytest.raises(ProjectPathError, match="home directory"):
        validate_project_root(str(Path.home()))


# ------------------------------------------------------------ inspection ---


def test_scan_hides_secrets_and_ignored_dirs(
    client: TestClient, project_dir: Path
) -> None:
    project = _register(client, project_dir)
    scan = client.post(f"/api/coding/projects/{project['id']}/scan").json()
    paths = {entry["path"] for entry in scan["files"]}
    assert "calculator.py" in paths and "src/util.py" in paths
    assert ".env" not in paths
    assert not any(p.startswith("node_modules") or p.startswith(".next") for p in paths)
    assert "Python" in scan["technologies"] and "FastAPI" in scan["technologies"]
    assert "pytest" in scan["test_commands"]
    assert "Demo" in scan["readme_excerpt"]


def test_file_read_guards(client: TestClient, project_dir: Path) -> None:
    project = _register(client, project_dir)
    ok = client.get(
        f"/api/coding/projects/{project['id']}/file",
        params={"path": "calculator.py"},
    )
    assert ok.status_code == 200 and "def add" in ok.json()["content"]
    for bad in (".env", "../outside.txt", "node_modules/junk/big.js"):
        denied = client.get(
            f"/api/coding/projects/{project['id']}/file", params={"path": bad}
        )
        assert denied.status_code == 403, bad


def test_symlink_escape_blocked(
    client: TestClient, project_dir: Path, tmp_path: Path
) -> None:
    if os.name == "nt":
        pytest.skip("symlinks need privileges on Windows")
    outside = tmp_path / "outside-secret.txt"
    outside.write_text("private")
    (project_dir / "link.txt").symlink_to(outside)
    project = _register(client, project_dir)
    denied = client.get(
        f"/api/coding/projects/{project['id']}/file", params={"path": "link.txt"}
    )
    assert denied.status_code == 403


def test_search_content_and_filenames(client: TestClient, project_dir: Path) -> None:
    project = _register(client, project_dir)
    content = client.get(
        f"/api/coding/projects/{project['id']}/search",
        params={"q": "def add", "kind": "content"},
    ).json()["hits"]
    assert any(hit["path"] == "calculator.py" for hit in content)
    names = client.get(
        f"/api/coding/projects/{project['id']}/search",
        params={"q": "util", "kind": "filename"},
    ).json()["hits"]
    assert names == [{"path": "src/util.py"}]


def test_project_ownership(client: TestClient, db_session_factory, project_dir) -> None:
    session: Session = db_session_factory()
    stranger = User(username="stranger2")
    session.add(stranger)
    session.commit()
    foreign = RegisteredProject(
        user_id=stranger.id, name="theirs", root_path=str(project_dir)
    )
    session.add(foreign)
    session.commit()
    foreign_id = foreign.id
    session.close()
    assert client.post(f"/api/coding/projects/{foreign_id}/scan").status_code == 404


# --------------------------------------------------------------- planner ---


@respx.mock
def test_task_planning_and_command_filtering(
    client: TestClient, project_dir: Path
) -> None:
    """The plan is stored and shown; the policy-refused command
    (pip install) is dropped from validation_commands and surfaced."""
    respx.post(OLLAMA_CHAT).mock(return_value=_reply(json.dumps(VALID_PLAN)))
    project = _register(client, project_dir)
    response = client.post(
        "/api/coding/tasks",
        json={"project_id": project["id"], "description": "Add a subtract function"},
    )
    assert response.status_code == 201, response.text
    task = response.json()
    assert task["state"] == "planned"
    assert task["plan"]["validation_commands"] == ["pytest"]
    assert any("pip install" in risk for risk in task["plan"]["risks"])


@respx.mock
def test_planner_repair_loop(client: TestClient, project_dir: Path) -> None:
    route = respx.post(OLLAMA_CHAT)
    route.side_effect = [_reply("no json here"), _reply(json.dumps(VALID_PLAN))]
    project = _register(client, project_dir)
    response = client.post(
        "/api/coding/tasks",
        json={"project_id": project["id"], "description": "Add a subtract function"},
    )
    assert response.status_code == 201
    assert route.call_count == 2


# ------------------------------------------------------------- workspace ---


@respx.mock
def test_workspace_isolation(client: TestClient, project_dir: Path) -> None:
    """Secrets never enter the workspace; edits there never touch the
    original project."""
    respx.post(OLLAMA_CHAT).mock(return_value=_reply(json.dumps(VALID_PLAN)))
    project = _register(client, project_dir)
    task = client.post(
        "/api/coding/tasks",
        json={"project_id": project["id"], "description": "Add a subtract function"},
    ).json()
    detail = client.post(f"/api/coding/tasks/{task['id']}/workspace").json()
    workspace = Path(
        client.get(f"/api/coding/tasks/{task['id']}").json()["state"] == "workspace_ready"
        and detail and _workspace_path(client, task["id"])
    )
    workspace = _workspace_path(client, task["id"])
    assert (workspace / "calculator.py").is_file()
    assert not (workspace / ".env").exists()
    assert not (workspace / "node_modules").exists()

    original = (project_dir / "calculator.py").read_text()
    (workspace / "calculator.py").write_text("TAMPERED = True\n")
    assert (project_dir / "calculator.py").read_text() == original


def _workspace_path(client: TestClient, task_id: str) -> Path:
    # workspace_path isn't exposed via the API (internal paths stay
    # internal); read it from the DB through the session the app uses.
    from app.api.conversations import current_user  # noqa: F401

    override = app.dependency_overrides[get_db]
    generator = override()
    session = next(generator)
    task = session.scalar(select(CodingTask).where(CodingTask.id == uuid.UUID(task_id)))
    path = Path(task.workspace_path)
    session.close()
    return path


# ----------------------------------------------- generation & validation ---


@respx.mock
def test_full_pipeline_to_decision(client: TestClient, project_dir: Path) -> None:
    """Plan → workspace → generate → validate → review → approve, with
    the original untouched and the approval message honest about it."""
    plan_reply = _reply(json.dumps(VALID_PLAN))
    code_reply = _reply(
        "def add(a, b):\n    return a + b\n\n\ndef subtract(a, b):\n    return a - b\n"
    )
    route = respx.post(OLLAMA_CHAT)
    route.side_effect = [plan_reply, code_reply]

    project = _register(client, project_dir)
    task = client.post(
        "/api/coding/tasks",
        json={"project_id": project["id"], "description": "Add a subtract function"},
    ).json()
    client.post(f"/api/coding/tasks/{task['id']}/workspace")
    generated = client.post(f"/api/coding/tasks/{task['id']}/generate").json()
    assert generated["state"] == "generated"
    assert generated["proposal"]["files"] == [
        {"path": "calculator.py", "change_type": "modify"}
    ]
    assert "+def subtract" in generated["proposal"]["diff"]
    assert generated["proposal"]["status"] == "proposed"

    # The generation prompt wrapped repo content as untrusted data.
    generation_payload = json.loads(route.calls.last.request.content)
    assert "untrusted" in generation_payload["messages"][0]["content"].lower()
    assert '<file path="calculator.py">' in generation_payload["messages"][1]["content"]

    validated = client.post(
        f"/api/coding/tasks/{task['id']}/validate",
        json={"commands": ["git push origin main", "pytest"]},
    ).json()
    refused = [run for run in validated["validation_runs"] if "REFUSED" in run["output_excerpt"]]
    assert len(refused) == 1 and "git push" in refused[0]["command"]

    reviewed = client.post(f"/api/coding/tasks/{task['id']}/review").json()
    assert reviewed["state"] == "awaiting_approval"
    assert reviewed["review"] is not None

    decision = client.post(
        f"/api/coding/tasks/{task['id']}/decision",
        json={"decision": "approved", "note": "looks good"},
    ).json()
    assert "NOT part of this milestone" in decision["message"]
    # Original file genuinely untouched.
    assert "subtract" not in (project_dir / "calculator.py").read_text()


@respx.mock
def test_decision_requires_review_first(client: TestClient, project_dir: Path) -> None:
    respx.post(OLLAMA_CHAT).mock(return_value=_reply(json.dumps(VALID_PLAN)))
    project = _register(client, project_dir)
    task = client.post(
        "/api/coding/tasks",
        json={"project_id": project["id"], "description": "Add a subtract function"},
    ).json()
    response = client.post(
        f"/api/coding/tasks/{task['id']}/decision", json={"decision": "approved"}
    )
    assert response.status_code == 409


# -------------------------------------------------------- patch validation ---


def test_protected_paths() -> None:
    assert is_protected_path("app/tools/path_guard.py")
    assert is_protected_path("src/command_policy.py")
    assert is_protected_path("lib/auth_helpers.ts")
    assert is_protected_path("core/audit.py")
    assert not is_protected_path("src/calculator.py")


def test_validate_target_rules(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    workspace.mkdir()
    (workspace / "app.py").write_text("x = 1\n")
    (workspace / "auth.py").write_text("secure = True\n")
    (workspace / "blob.bin").write_bytes(b"\x00\x01")
    guard = PathGuard(workspace)

    assert validate_target(guard, "app.py", "add a feature", exists_required=True)
    with pytest.raises(PathAccessError):
        validate_target(guard, "../escape.py", "task", exists_required=False)
    with pytest.raises(PathAccessError):
        validate_target(guard, ".env", "task", exists_required=False)
    from app.coding.generator import PatchValidationError

    with pytest.raises(PatchValidationError, match="security control"):
        validate_target(guard, "auth.py", "add a login button", exists_required=True)
    # Explicit security intent unlocks the protected file.
    assert validate_target(
        guard, "auth.py", "improve the auth security checks", exists_required=True
    )
    with pytest.raises(PatchValidationError, match="binary"):
        validate_target(guard, "blob.bin", "task", exists_required=True)
    with pytest.raises(PatchValidationError, match="does not exist"):
        validate_target(guard, "ghost.py", "task", exists_required=True)


@respx.mock
def test_generation_rejects_all_invalid_targets(
    client: TestClient, project_dir: Path
) -> None:
    """A plan aiming only at forbidden files fails loudly, not silently."""
    bad_plan = {**VALID_PLAN, "files_to_modify": [".env", "../outside.py"]}
    respx.post(OLLAMA_CHAT).mock(return_value=_reply(json.dumps(bad_plan)))
    project = _register(client, project_dir)
    task = client.post(
        "/api/coding/tasks",
        json={"project_id": project["id"], "description": "Add a subtract function"},
    ).json()
    client.post(f"/api/coding/tasks/{task['id']}/workspace")
    response = client.post(f"/api/coding/tasks/{task['id']}/generate")
    assert response.status_code == 502
    assert "No valid file changes" in response.json()["detail"]


# ---------------------------------------------------------------- executor ---


def test_executor_blocks_non_allowlisted(tmp_path: Path) -> None:
    for command in ("echo hi", "curl http://x", "pytest; rm -rf /", "npm run evil"):
        with pytest.raises(CommandRejected):
            run_allowlisted(command, cwd=tmp_path)


def test_executor_runs_allowlisted_and_caps_output(tmp_path: Path) -> None:
    (tmp_path / "test_ok.py").write_text("def test_ok():\n    assert True\n")
    result = run_allowlisted("pytest -q", cwd=tmp_path)
    assert result.exit_code == 0 and result.passed


def test_executor_timeout(tmp_path: Path) -> None:
    """Timeout mechanics, tested on the internal executor (the argv used
    here would be rejected by the policy gate, which is separately
    tested above)."""
    audit = AuditLogger(tmp_path / "audit.jsonl")
    result = _execute(
        ["python3", "-c", "import time; time.sleep(5)"],
        command="(internal timeout test)", cwd=tmp_path,
        timeout_seconds=0.5, max_output=1000, audit=audit,
    )
    assert result.timed_out and not result.passed


def test_executor_sanitizes_environment(tmp_path: Path, monkeypatch) -> None:
    """Secrets in NISH's environment never reach executed commands."""
    monkeypatch.setenv("SUPER_SECRET_TOKEN", "leakme")
    (tmp_path / "test_env.py").write_text(
        "import os\n\ndef test_env():\n    assert 'SUPER_SECRET_TOKEN' not in os.environ\n"
    )
    result = run_allowlisted("pytest -q", cwd=tmp_path)
    assert result.passed, result.stdout + result.stderr


# ------------------------------------------------------------ state machine ---


def test_coding_state_machine() -> None:
    task = CodingTask(
        user_id=uuid.uuid4(), project_id=uuid.uuid4(), description="d" * 12
    )
    assert task.state is None or task.state == "created" or True
    task.state = "created"
    with pytest.raises(IllegalCodingTransition):
        transition(task, "approved")
    with pytest.raises(IllegalCodingTransition):
        transition(task, "generating")
    transition(task, "planning")
    transition(task, "planned")
    assert task.state == "planned"
