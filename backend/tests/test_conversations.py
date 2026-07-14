"""Tests for conversation persistence (memory milestone, part 1).

The API runs against an in-memory SQLite database via a dependency
override — fast, isolated, no external services. Schema portability is
guaranteed by using only portable column types in the models; the real
PostgreSQL schema is exercised by the Alembic migration (verified
separately against a live Postgres).

Ollama is mocked with respx as usual. Run with:
    pytest tests/test_conversations.py
"""

import uuid

import httpx
import pytest
import respx
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import get_settings
from app.database.models import Base, Conversation, Message, User
from app.database.session import get_db
from app.main import app

OLLAMA_CHAT = "http://localhost:11434/api/chat"


def _ollama_reply(content: str) -> httpx.Response:
    return httpx.Response(
        200, json={"message": {"role": "assistant", "content": content}}
    )


@pytest.fixture()
def db_session_factory():
    """Fresh in-memory SQLite database per test."""
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


# ------------------------------------------------------------------ CRUD ---


def test_create_and_list_conversations(client: TestClient) -> None:
    created = client.post("/api/conversations", json={"title": "My project"})
    assert created.status_code == 201
    assert created.json()["title"] == "My project"
    assert created.json()["message_count"] == 0

    default = client.post("/api/conversations", json={})
    assert default.json()["title"] == "New chat"

    listing = client.get("/api/conversations")
    assert listing.status_code == 200
    assert len(listing.json()) == 2


def test_rename_conversation(client: TestClient) -> None:
    conversation_id = client.post("/api/conversations", json={}).json()["id"]
    renamed = client.patch(
        f"/api/conversations/{conversation_id}", json={"title": "Better name"}
    )
    assert renamed.status_code == 200
    assert renamed.json()["title"] == "Better name"


def test_rename_validation(client: TestClient) -> None:
    conversation_id = client.post("/api/conversations", json={}).json()["id"]
    too_long = client.patch(
        f"/api/conversations/{conversation_id}", json={"title": "x" * 121}
    )
    assert too_long.status_code == 422
    empty = client.patch(
        f"/api/conversations/{conversation_id}", json={"title": ""}
    )
    assert empty.status_code == 422


def test_delete_conversation(client: TestClient) -> None:
    conversation_id = client.post("/api/conversations", json={}).json()["id"]
    assert client.delete(f"/api/conversations/{conversation_id}").status_code == 204
    assert client.get(f"/api/conversations/{conversation_id}").status_code == 404


def test_missing_conversation_is_404(client: TestClient) -> None:
    ghost = uuid.uuid4()
    assert client.get(f"/api/conversations/{ghost}").status_code == 404
    assert (
        client.patch(f"/api/conversations/{ghost}", json={"title": "x"}).status_code
        == 404
    )
    assert client.delete(f"/api/conversations/{ghost}").status_code == 404


# ------------------------------------------------------------ persistence ---


@respx.mock
def test_message_exchange_is_persisted(client: TestClient) -> None:
    respx.post(OLLAMA_CHAT).mock(return_value=_ollama_reply("Hi! I'm NISH."))
    conversation_id = client.post("/api/conversations", json={}).json()["id"]

    sent = client.post(
        f"/api/conversations/{conversation_id}/messages",
        json={"content": "Hello NISH"},
    )
    assert sent.status_code == 200
    body = sent.json()
    assert body["user_message"]["role"] == "user"
    assert body["assistant_message"]["content"] == "Hi! I'm NISH."

    # Both messages are readable back from the database.
    detail = client.get(f"/api/conversations/{conversation_id}").json()
    assert [m["role"] for m in detail["messages"]] == ["user", "assistant"]
    assert detail["messages"][0]["content"] == "Hello NISH"


@respx.mock
def test_new_chat_is_auto_titled_from_first_message(client: TestClient) -> None:
    respx.post(OLLAMA_CHAT).mock(return_value=_ollama_reply("ok"))
    conversation_id = client.post("/api/conversations", json={}).json()["id"]
    client.post(
        f"/api/conversations/{conversation_id}/messages",
        json={"content": "Help me plan a FastAPI project"},
    )
    listing = client.get("/api/conversations").json()
    assert listing[0]["title"] == "Help me plan a FastAPI project"


@respx.mock
def test_continuing_conversation_sends_stored_history(client: TestClient) -> None:
    """The model must receive earlier turns loaded from the database."""
    route = respx.post(OLLAMA_CHAT).mock(return_value=_ollama_reply("reply"))
    conversation_id = client.post("/api/conversations", json={}).json()["id"]

    client.post(
        f"/api/conversations/{conversation_id}/messages",
        json={"content": "First question"},
    )
    client.post(
        f"/api/conversations/{conversation_id}/messages",
        json={"content": "Follow-up"},
    )

    import json as jsonlib

    payload = jsonlib.loads(route.calls.last.request.content)
    roles_and_contents = [
        (m["role"], m["content"]) for m in payload["messages"]
    ]
    # system prompt + stored history + new message, in order.
    assert roles_and_contents[0][0] == "system"
    assert roles_and_contents[1] == ("user", "First question")
    assert roles_and_contents[2] == ("assistant", "reply")
    assert roles_and_contents[3] == ("user", "Follow-up")


@respx.mock
def test_history_sent_to_model_is_capped(client: TestClient) -> None:
    settings = get_settings()
    route = respx.post(OLLAMA_CHAT).mock(return_value=_ollama_reply("r"))
    conversation_id = client.post("/api/conversations", json={}).json()["id"]
    for index in range(settings.max_history_messages // 2 + 3):
        client.post(
            f"/api/conversations/{conversation_id}/messages",
            json={"content": f"msg {index}"},
        )
    import json as jsonlib

    payload = jsonlib.loads(route.calls.last.request.content)
    # system prompt + at most max_history_messages turns.
    assert len(payload["messages"]) <= settings.max_history_messages + 1


@respx.mock
def test_user_message_survives_model_failure(client: TestClient) -> None:
    """If Ollama dies, the typed message must already be saved."""
    respx.post(OLLAMA_CHAT).mock(side_effect=httpx.ConnectError("refused"))
    conversation_id = client.post("/api/conversations", json={}).json()["id"]
    failed = client.post(
        f"/api/conversations/{conversation_id}/messages",
        json={"content": "Please don't lose this"},
    )
    assert failed.status_code == 503

    detail = client.get(f"/api/conversations/{conversation_id}").json()
    assert len(detail["messages"]) == 1
    assert detail["messages"][0]["content"] == "Please don't lose this"


def test_oversized_message_is_rejected(client: TestClient) -> None:
    settings = get_settings()
    conversation_id = client.post("/api/conversations", json={}).json()["id"]
    response = client.post(
        f"/api/conversations/{conversation_id}/messages",
        json={"content": "x" * (settings.max_message_chars + 1)},
    )
    assert response.status_code == 413


def test_empty_message_is_rejected(client: TestClient) -> None:
    conversation_id = client.post("/api/conversations", json={}).json()["id"]
    response = client.post(
        f"/api/conversations/{conversation_id}/messages", json={"content": ""}
    )
    assert response.status_code == 422


# -------------------------------------------------------------- ownership ---


def test_other_users_conversations_are_invisible(
    client: TestClient, db_session_factory
) -> None:
    """Ownership check: someone else's conversation 404s, not 403s."""
    session: Session = db_session_factory()
    stranger = User(username="someone-else")
    session.add(stranger)
    session.commit()
    foreign = Conversation(user_id=stranger.id, title="private stuff")
    session.add(foreign)
    session.commit()
    foreign_id = foreign.id
    session.close()

    assert client.get(f"/api/conversations/{foreign_id}").status_code == 404
    assert client.delete(f"/api/conversations/{foreign_id}").status_code == 404
    listing = client.get("/api/conversations").json()
    assert all(item["id"] != str(foreign_id) for item in listing)


# ---------------------------------------------------------------- cascade ---


def test_deleting_conversation_cascades_messages(
    client: TestClient, db_session_factory
) -> None:
    with respx.mock:
        respx.post(OLLAMA_CHAT).mock(return_value=_ollama_reply("bye"))
        conversation_id = client.post("/api/conversations", json={}).json()["id"]
        client.post(
            f"/api/conversations/{conversation_id}/messages",
            json={"content": "hello"},
        )
    client.delete(f"/api/conversations/{conversation_id}")

    session: Session = db_session_factory()
    remaining = session.scalars(select(Message)).all()
    session.close()
    assert remaining == []
