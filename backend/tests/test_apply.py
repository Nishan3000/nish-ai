"""Tests for reviewed change application (v0.7).

These tests drive the REAL apply pipeline against real temporary Git
repositories (git init in tmp_path), with only the model mocked. The
pipeline up to `awaiting_approval` is fast-forwarded by inserting the
proposal rows directly — the generation path is already covered by
test_coding.py.
"""

import subprocess
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.coding import gitops
from app.coding.apply import compute_proposal_hash
from app.database.models import (
    Base,
    ChangeApplication,
    CodingProposal,
    CodingProposalFile,
    CodingTask,
    RegisteredProject,
    User,
    get_or_create_local_user,
)
from app.database.session import get_db
from app.main import app

PASSING_TEST = "def test_ok():\n    assert 1 + 1 == 2\n"
FAILING_TEST = "def test_broken():\n    assert 1 + 1 == 3\n"
NEW_MODULE = "def greet(name):\n    return f'hello {name}'\n"


def _git(repo, *args):
    subprocess.run(
        ["git", *args], cwd=repo, check=True, capture_output=True, text=True
    )


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
def client(db_session_factory) -> TestClient:
    def override_get_db():
        session = db_session_factory()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture()
def repo(tmp_path):
    """A real git repository with an identity, one commit, main branch."""
    root = tmp_path / "project"
    root.mkdir()
    (root / "test_sample.py").write_text(PASSING_TEST)
    (root / "README.md").write_text("# Sample\n")
    _git(root, "init", "-b", "main")
    _git(root, "config", "user.email", "dev@example.com")
    _git(root, "config", "user.name", "Dev")
    _git(root, "add", ".")
    _git(root, "commit", "-m", "initial")
    return root


def _seed_approved_task(
    session_factory, repo, *, new_test_content=PASSING_TEST, extra_file=True
):
    """Insert project + task + proposal + files, then return ids. The
    task is left in `awaiting_approval` so tests exercise the REAL
    decision endpoint for approval."""
    session = session_factory()
    user = get_or_create_local_user(session)
    project = RegisteredProject(
        user_id=user.id,
        name="sample",
        root_path=str(repo),
        description="",
        default_branch="main",
    )
    session.add(project)
    session.commit()
    task = CodingTask(
        user_id=user.id,
        project_id=project.id,
        description="add greet helper module",
        state="awaiting_approval",
        plan={
            "task_summary": "Add greet helper",
            "assumptions": [],
            "files_to_inspect": [],
            "files_to_modify": ["test_sample.py"],
            "files_to_create": ["greet.py"] if extra_file else [],
            "steps": ["write module", "extend test"],
            "validation_commands": ["pytest"],
            "risks": [],
            "approval_requirements": [],
        },
    )
    session.add(task)
    session.commit()
    proposal = CodingProposal(
        task_id=task.id, status="proposed", summary="Add greet helper", diff="+greet"
    )
    session.add(proposal)
    session.commit()
    files = [
        CodingProposalFile(
            proposal_id=proposal.id,
            path="test_sample.py",
            change_type="modify",
            original_content=PASSING_TEST,
            new_content=new_test_content,
        )
    ]
    if extra_file:
        files.append(
            CodingProposalFile(
                proposal_id=proposal.id,
                path="greet.py",
                change_type="create",
                original_content="",
                new_content=NEW_MODULE,
            )
        )
    session.add_all(files)
    session.commit()
    ids = {"task": str(task.id), "proposal": str(proposal.id)}
    session.close()
    return ids


def _approve(client, task_id) -> dict:
    response = client.post(
        f"/api/coding/tasks/{task_id}/decision",
        json={"decision": "approved", "note": "reviewed"},
    )
    assert response.status_code == 200
    return response.json()


# ------------------------------------------------------------- approval ---


def test_approval_records_hash_and_expiry(client, db_session_factory, repo):
    ids = _seed_approved_task(db_session_factory, repo)
    decision = _approve(client, ids["task"])
    assert len(decision["proposal_hash"]) == 64
    assert decision["expires_at"] is not None

    task = client.get(f"/api/coding/tasks/{ids['task']}").json()
    assert task["approval"]["decision"] == "approved"
    assert task["approval"]["proposal_hash"] == decision["proposal_hash"]


def test_apply_without_approval_refused(client, db_session_factory, repo):
    ids = _seed_approved_task(db_session_factory, repo)
    response = client.post(
        f"/api/coding/tasks/{ids['task']}/apply",
        json={"confirm": True, "proposal_hash": "0" * 64},
    )
    assert response.status_code == 409
    assert "approved" in response.json()["detail"]


def test_apply_requires_second_confirmation(client, db_session_factory, repo):
    ids = _seed_approved_task(db_session_factory, repo)
    decision = _approve(client, ids["task"])
    response = client.post(
        f"/api/coding/tasks/{ids['task']}/apply",
        json={"confirm": False, "proposal_hash": decision["proposal_hash"]},
    )
    assert response.status_code == 400
    assert "confirmation" in response.json()["detail"]


def test_apply_with_wrong_echoed_hash_refused(client, db_session_factory, repo):
    ids = _seed_approved_task(db_session_factory, repo)
    _approve(client, ids["task"])
    response = client.post(
        f"/api/coding/tasks/{ids['task']}/apply",
        json={"confirm": True, "proposal_hash": "f" * 64},
    )
    assert response.status_code == 409


def test_expired_approval_refused(client, db_session_factory, repo):
    ids = _seed_approved_task(db_session_factory, repo)
    decision = _approve(client, ids["task"])
    session = db_session_factory()
    from app.database.models import Approval

    approval = session.scalars(select(Approval)).all()[-1]
    approval.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    session.commit()
    session.close()
    response = client.post(
        f"/api/coding/tasks/{ids['task']}/apply",
        json={"confirm": True, "proposal_hash": decision["proposal_hash"]},
    )
    assert response.status_code == 409
    assert "expired" in response.json()["detail"].lower()


def test_tampered_proposal_hash_mismatch(client, db_session_factory, repo):
    ids = _seed_approved_task(db_session_factory, repo)
    decision = _approve(client, ids["task"])
    # Tamper with the proposal content AFTER approval.
    session = db_session_factory()
    row = session.scalars(
        select(CodingProposalFile).where(
            CodingProposalFile.path == "greet.py"
        )
    ).one()
    row.new_content = "import os\nos.system('evil')\n"
    session.commit()
    session.close()
    response = client.post(
        f"/api/coding/tasks/{ids['task']}/apply",
        json={"confirm": True, "proposal_hash": decision["proposal_hash"]},
    )
    assert response.status_code == 409
    assert "changed after" in response.json()["detail"]
    # And nothing touched the repository.
    assert gitops.is_clean(repo)
    assert not (repo / "greet.py").exists()


# ---------------------------------------------------------------- apply ---


def test_apply_happy_path_commits_locally(client, db_session_factory, repo):
    ids = _seed_approved_task(db_session_factory, repo)
    decision = _approve(client, ids["task"])
    response = client.post(
        f"/api/coding/tasks/{ids['task']}/apply",
        json={"confirm": True, "proposal_hash": decision["proposal_hash"]},
    )
    assert response.status_code == 200
    application = response.json()
    assert application["status"] == "committed"
    assert application["branch_name"].startswith("nish/task-")
    assert application["original_branch"] == "main"
    assert application["commit_hash"]
    assert "+def greet" in application["final_diff"]

    # The branch exists with exactly one commit on the recorded base.
    assert gitops.branch_exists(repo, application["branch_name"])
    tip = gitops.branch_head(repo, application["branch_name"])
    assert tip == application["commit_hash"]
    assert gitops.commit_parent(repo, tip) == application["original_head"]

    # Commit metadata: message format + task/proposal ids + honest
    # attribution, authored with the repo's configured identity.
    log = subprocess.run(
        ["git", "log", "-1", "--format=%B%n%an <%ae>", application["branch_name"]],
        cwd=repo, capture_output=True, text=True, check=True,
    ).stdout
    assert log.startswith("NISH: ")
    assert ids["task"] in log and ids["proposal"] in log
    assert "after explicit user approval" in log
    assert "Dev <dev@example.com>" in log

    # main is untouched and the working tree is clean.
    assert gitops.current_branch(repo) in ("main", application["branch_name"])
    main_files = subprocess.run(
        ["git", "show", "main:test_sample.py"],
        cwd=repo, capture_output=True, text=True, check=True,
    ).stdout
    assert main_files == PASSING_TEST

    # Validation reran in the apply phase and was recorded.
    task = client.get(f"/api/coding/tasks/{ids['task']}").json()
    assert any(run["passed"] for run in task["validation_runs"])
    assert task["application"]["status"] == "committed"


def test_apply_is_idempotent(client, db_session_factory, repo):
    ids = _seed_approved_task(db_session_factory, repo)
    decision = _approve(client, ids["task"])
    body = {"confirm": True, "proposal_hash": decision["proposal_hash"]}
    first = client.post(f"/api/coding/tasks/{ids['task']}/apply", json=body).json()
    second = client.post(f"/api/coding/tasks/{ids['task']}/apply", json=body).json()
    assert first["id"] == second["id"]
    assert first["commit_hash"] == second["commit_hash"]
    # Only ONE nish branch and one commit exist.
    branches = subprocess.run(
        ["git", "branch", "--list", "nish/*"],
        cwd=repo, capture_output=True, text=True, check=True,
    ).stdout.strip().splitlines()
    assert len(branches) == 1


def test_dirty_repository_refused_with_explanation(
    client, db_session_factory, repo
):
    (repo / "wip.txt").write_text("uncommitted work\n")
    ids = _seed_approved_task(db_session_factory, repo)
    decision = _approve(client, ids["task"])
    response = client.post(
        f"/api/coding/tasks/{ids['task']}/apply",
        json={"confirm": True, "proposal_hash": decision["proposal_hash"]},
    )
    assert response.status_code == 409
    assert "uncommitted changes" in response.json()["detail"]
    # User work preserved, nothing applied.
    assert (repo / "wip.txt").exists()
    assert not (repo / "greet.py").exists()


def test_non_git_project_refused(client, db_session_factory, tmp_path):
    plain = tmp_path / "plain"
    plain.mkdir()
    (plain / "a.py").write_text("x = 1\n")
    ids = _seed_approved_task(db_session_factory, plain)
    decision = _approve(client, ids["task"])
    response = client.post(
        f"/api/coding/tasks/{ids['task']}/apply",
        json={"confirm": True, "proposal_hash": decision["proposal_hash"]},
    )
    assert response.status_code == 409
    assert "not a Git repository" in response.json()["detail"]


def test_existing_foreign_branch_refused(client, db_session_factory, repo):
    ids = _seed_approved_task(db_session_factory, repo)
    decision = _approve(client, ids["task"])
    # Pre-create the branch name the task would use.
    task_short = uuid.UUID(ids["task"]).hex[:8]
    _git(repo, "branch", f"nish/task-{task_short}-add-greet-helper-module")
    response = client.post(
        f"/api/coding/tasks/{ids['task']}/apply",
        json={"confirm": True, "proposal_hash": decision["proposal_hash"]},
    )
    assert response.status_code == 409
    assert "already exists" in response.json()["detail"]


def test_validation_failure_means_no_commit_and_restored_repo(
    client, db_session_factory, repo
):
    ids = _seed_approved_task(
        db_session_factory, repo, new_test_content=FAILING_TEST
    )
    decision = _approve(client, ids["task"])
    response = client.post(
        f"/api/coding/tasks/{ids['task']}/apply",
        json={"confirm": True, "proposal_hash": decision["proposal_hash"]},
    )
    assert response.status_code == 200
    application = response.json()
    assert application["status"] == "validation_failed"
    assert application["commit_hash"] is None
    assert "no commit was created" in application["error"]

    # Repository fully restored: original content, clean tree, no branch,
    # back on main.
    assert (repo / "test_sample.py").read_text() == PASSING_TEST
    assert not (repo / "greet.py").exists()
    assert gitops.is_clean(repo)
    assert gitops.current_branch(repo) == "main"
    assert not gitops.branch_exists(repo, application["branch_name"])

    # The failing run is visible with its output for debugging.
    task = client.get(f"/api/coding/tasks/{ids['task']}").json()
    failed_runs = [run for run in task["validation_runs"] if not run["passed"]]
    assert failed_runs


def test_protected_path_revalidated_at_apply_time(
    client, db_session_factory, repo
):
    """Even a proposal that somehow contains a traversal path is caught
    again at application time (paths are revalidated, not trusted)."""
    ids = _seed_approved_task(db_session_factory, repo)
    session = db_session_factory()
    row = session.scalars(
        select(CodingProposalFile).where(CodingProposalFile.path == "greet.py")
    ).one()
    row.path = "../escape.py"
    session.commit()
    session.close()
    decision = _approve(client, ids["task"])  # hash binds the tampered set
    response = client.post(
        f"/api/coding/tasks/{ids['task']}/apply",
        json={"confirm": True, "proposal_hash": decision["proposal_hash"]},
    )
    assert response.status_code in (400, 403, 409, 422)
    assert not (repo.parent / "escape.py").exists()
    assert gitops.is_clean(repo)


# ------------------------------------------------------------- rollback ---


def _applied(client, db_session_factory, repo):
    ids = _seed_approved_task(db_session_factory, repo)
    decision = _approve(client, ids["task"])
    application = client.post(
        f"/api/coding/tasks/{ids['task']}/apply",
        json={"confirm": True, "proposal_hash": decision["proposal_hash"]},
    ).json()
    assert application["status"] == "committed"
    return ids, application


def test_rollback_removes_only_task_branch(client, db_session_factory, repo):
    ids, application = _applied(client, db_session_factory, repo)
    response = client.post(
        f"/api/coding/tasks/{ids['task']}/rollback", json={"confirm": True}
    )
    assert response.status_code == 200
    assert response.json()["status"] == "rolled_back"
    assert not gitops.branch_exists(repo, application["branch_name"])
    assert gitops.current_branch(repo) == "main"
    assert gitops.head_commit(repo) == application["original_head"]
    # Original files intact on main.
    assert (repo / "test_sample.py").read_text() == PASSING_TEST


def test_rollback_requires_confirmation(client, db_session_factory, repo):
    ids, _ = _applied(client, db_session_factory, repo)
    response = client.post(
        f"/api/coding/tasks/{ids['task']}/rollback", json={"confirm": False}
    )
    assert response.status_code == 400


def test_rollback_refused_when_user_built_on_branch(
    client, db_session_factory, repo
):
    ids, application = _applied(client, db_session_factory, repo)
    # User adds their own commit on the task branch.
    _git(repo, "checkout", application["branch_name"])
    (repo / "user_work.py").write_text("value = 42\n")
    _git(repo, "add", "user_work.py")
    _git(repo, "commit", "-m", "user work")
    _git(repo, "checkout", "main")

    response = client.post(
        f"/api/coding/tasks/{ids['task']}/rollback", json={"confirm": True}
    )
    assert response.status_code == 409
    assert "refuses to roll back over your work" in response.json()["detail"]
    # Branch and the user's commit survive.
    assert gitops.branch_exists(repo, application["branch_name"])


def test_rollback_twice_is_refused_cleanly(client, db_session_factory, repo):
    ids, _ = _applied(client, db_session_factory, repo)
    assert (
        client.post(
            f"/api/coding/tasks/{ids['task']}/rollback", json={"confirm": True}
        ).status_code
        == 200
    )
    second = client.post(
        f"/api/coding/tasks/{ids['task']}/rollback", json={"confirm": True}
    )
    assert second.status_code == 409
    assert "rolled_back" in second.json()["detail"]


# ------------------------------------------------------ gitops hard rails ---


def test_gitops_refuses_forbidden_operations(repo):
    for args in (
        ["push", "origin", "main"],
        ["pull"],
        ["fetch", "--all"],
        ["merge", "main"],
        ["rebase", "main"],
        ["reset", "--hard", "HEAD~1"],
        ["remote", "add", "origin", "https://example.com/x.git"],
        ["config", "user.name", "Evil"],
        ["checkout", "-b", "nish/x", "--force"],
    ):
        with pytest.raises(gitops.GitError):
            gitops._run(repo, args)


def test_gitops_never_deletes_non_nish_branches(repo):
    _git(repo, "branch", "feature/user-branch")
    with pytest.raises(gitops.GitError):
        gitops.delete_nish_branch(repo, "feature/user-branch")
    with pytest.raises(gitops.GitError):
        gitops.delete_nish_branch(repo, "main")


def test_commit_details_endpoint(client, db_session_factory, repo):
    ids, application = _applied(client, db_session_factory, repo)
    response = client.get(f"/api/coding/tasks/{ids['task']}/application/commit")
    assert response.status_code == 200
    body = response.json()
    assert body["commit_hash"] == application["commit_hash"]
    assert "NISH:" in body["details"]


def test_application_ownership(client, db_session_factory, repo):
    ids, _ = _applied(client, db_session_factory, repo)
    session = db_session_factory()
    stranger = User(username="stranger")
    session.add(stranger)
    session.commit()
    application = session.scalars(select(ChangeApplication)).one()
    application.user_id = stranger.id
    session.commit()
    session.close()
    response = client.get(f"/api/coding/tasks/{ids['task']}/application")
    assert response.status_code == 404


def test_hash_is_deterministic_and_content_sensitive(db_session_factory, repo):
    ids = _seed_approved_task(db_session_factory, repo)
    session = db_session_factory()
    proposal = session.scalars(select(CodingProposal)).one()
    files = list(proposal.files)
    first = compute_proposal_hash(proposal, files)
    assert first == compute_proposal_hash(proposal, list(reversed(files)))
    files[0].new_content += " "
    assert first != compute_proposal_hash(proposal, files)
    session.close()
