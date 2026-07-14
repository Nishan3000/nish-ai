# NISH

**Think. Learn. Build.**

A private, self-hosted AI assistant. Local models via Ollama, FastAPI backend, Next.js frontend.

**Current status: Phase 1** — basic chat against a local Ollama model.

## Requirements

| Software | Version | Purpose |
|----------|---------|---------|
| Python   | 3.11+ (3.12 recommended) | Backend |
| Node.js  | 20+ (22 LTS recommended) | Frontend |
| Ollama   | latest | Local model server — https://ollama.com/download |
| Docker Desktop | optional | Containerised run |

## 1. Get a model

```bash
ollama pull qwen3:8b        # default; needs ~6 GB RAM/VRAM
# smaller alternative for low-spec machines:
ollama pull llama3.2:3b
```

If you use a different model, set `OLLAMA_MODEL` in `backend/.env`.

Verify Ollama is running: open http://localhost:11434 — it should say "Ollama is running".

## 2. Backend

**macOS / Linux**
```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload --port 8000
```

**Windows PowerShell**
```powershell
cd backend
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
uvicorn app.main:app --reload --port 8000
```

> If PowerShell blocks activation, run once:
> `Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser`

Verify: http://localhost:8000/api/health should return
`{"status":"ok", ..., "ollama":"reachable", ...}`.
Interactive API docs: http://localhost:8000/docs

## 3. Frontend

**macOS / Linux**
```bash
cd frontend
npm install
cp .env.local.example .env.local
npm run dev
```

**Windows PowerShell**
```powershell
cd frontend
npm install
Copy-Item .env.local.example .env.local
npm run dev
```

Open http://localhost:3000 and send a message.

## 4. Run the tests

```bash
cd backend
pytest
```

All 10 tests should pass. They mock Ollama, so they work even with Ollama stopped.

## 5. Docker (optional)

Keep Ollama running on your host machine, then:

```bash
docker compose up --build
```

Frontend: http://localhost:3000 · Backend: http://localhost:8000/api/health

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| Header shows "Backend offline" | Start the backend (step 2); check it's on port 8000. |
| Header shows "Ollama offline" | Start Ollama (`ollama serve` or the desktop app). |
| Chat error mentions `ollama pull` | The configured model isn't downloaded — run the suggested command. |
| CORS error in browser console | Frontend origin must be listed in `CORS_ORIGINS` in `backend/.env`. |
| Response takes very long first time | Normal — Ollama loads the model into memory on first request. |

## Project layout

```
nish/
  backend/    FastAPI + Ollama service (Python)
  frontend/   Next.js chat UI (TypeScript)
  docker-compose.yml
```

Empty backend folders (`agents/`, `auth/`, `memory/`, …) are reserved for later phases.

## Memory milestone — part 1 (persistent conversations)

Conversations and messages are now stored in PostgreSQL.

### Database setup

Easiest (Docker):
```bash
docker compose up db          # starts PostgreSQL with the right user/db
```
Or install PostgreSQL yourself and create a database matching
`DATABASE_URL` in `backend/.env` (see `.env.example`).

### Migrations

```bash
cd backend
alembic upgrade head          # creates users, conversations, messages
```

### New endpoints

```bash
curl -X POST http://localhost:8000/api/conversations -H "Content-Type: application/json" -d '{}'
curl http://localhost:8000/api/conversations
curl -X POST http://localhost:8000/api/conversations/<id>/messages \
  -H "Content-Type: application/json" -d '{"content": "Hello NISH"}'
curl -X PATCH http://localhost:8000/api/conversations/<id> \
  -H "Content-Type: application/json" -d '{"title": "Renamed"}'
curl -X DELETE http://localhost:8000/api/conversations/<id>
```

The original stateless `/api/chat` endpoint is unchanged.

### Verifying persistence

Send a couple of messages to a conversation, stop the backend
(Ctrl+C), start it again, then `GET /api/conversations/<id>` — the
full history returns from PostgreSQL. Tests: `pytest tests/test_conversations.py`.

## Agent phase — part 1 (planning & safe inspection)

New endpoints (backend must be running; keep it bound to localhost — there is no auth yet):

```bash
# Point the agent at a project to inspect (default: backend/workspace)
# then create a task — NISH plans it using your local model:
curl -X POST http://localhost:8000/api/agent/tasks \
  -H "Content-Type: application/json" \
  -d '{"description": "Add input validation to the user endpoints"}'

curl http://localhost:8000/api/agent/tasks            # list tasks
curl http://localhost:8000/api/agent/repo/tree        # guarded file listing
curl "http://localhost:8000/api/agent/repo/file?path=src/main.py"
curl http://localhost:8000/api/agent/audit/verify     # audit chain check
```

Agent tests only: `pytest tests/test_agent_security.py tests/test_agent_pipeline.py`

What the agent can and cannot do at this stage: it can plan tasks and read
files inside `AGENT_WORKSPACE_ROOT` (secrets, `.git`, and anything outside
the root are unreadable; every access is written to a hash-chained audit
log at `AGENT_AUDIT_LOG_PATH`). It cannot write files, run commands, or
touch Git — those arrive in the next part, gated by the command allowlist
and approval flow that already exist in `app/tools/command_policy.py`.
