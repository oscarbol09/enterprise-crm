# Enterprise CRM

Multi-tenant B2B Customer Relationship Management platform built with FastAPI, PostgreSQL 16 (Forced Row-Level Security + `pgvector`), Redis, and Next.js 16 (React 19 + TypeScript).

## Why This Exists

Most multi-tenant SaaS backends enforce isolation solely through application-level `WHERE tenant_id = ...` filters, leaving a single omitted filter or raw query exposed to cross-tenant data leakage. Similarly, most AI-enabled CRMs couple database transactions directly to external LLM calls or let models mutate records without an audit boundary.

This repository demonstrates an isolated reference architecture combining:

- **Database-enforced multi-tenancy**: PostgreSQL `ENABLE` + `FORCE ROW LEVEL SECURITY` on all 14 tenant-scoped tables under a least-privilege `crm_app` (`NOBYPASSRLS`) role, bound per transaction via `SELECT set_config('app.current_tenant_id', :tenant_id, true)`.
- **Tenant-scoped BYOK cryptographic vault**: Customer LLM API keys (Gemini, Claude, OpenAI) encrypted with AES-256-GCM bound to the tenant UUID as Associated Authenticated Data (`AAD`).
- **Zero-I/O segmented AI Copilot with Human-in-the-Loop (HITL)**: Database reads close before outbound HTTP requests to LLM providers; write actions proposed by the AI are stored as `pending_review` proposals and only mutate CRM tables (`tasks`, `deals`) upon explicit approval.

## Architecture Summary

| Layer | Technology | Key Responsibilities |
| :--- | :--- | :--- |
| API & Domain | FastAPI, Python 3.12, SQLAlchemy 2 Async, Pydantic v2 | Auth + refresh rotation, RBAC (`admin`, `sales_manager`, `sales_rep`, `readonly`), contacts/deals/accounts/tasks CRUD, HITL engine, MCP tool endpoints |
| Persistence | PostgreSQL 16 + `pgvector` + Alembic | Shared tables with `FORCE ROW LEVEL SECURITY`, HNSW cosine index (`vector(768)`), `SECURITY DEFINER` pre-auth lookup functions, transactional `outbox_events` (`SKIP LOCKED`) |
| Caching & Rate Limits | Redis 7 | Sliding-window rate limiting on auth and AI endpoints with in-memory fallback |
| Web Client | Next.js 16.4 (App Router), React 19, Tailwind CSS | In-memory access token with single silent refresh retry (`httpOnly` cookie), optimistic Kanban pipeline with rollback & mandatory loss reason, Command Palette (`Ctrl/Cmd+K`), AI Copilot & HITL queue, BYOK manager |
| Verification & CI | Pytest + Hypothesis + Vitest + MSW + Trivy + Gitleaks | 89.5% backend branch coverage locally (SQLite + FakeRedis), live Postgres Forced RLS integration tests in CI, 81.2% frontend statement coverage |

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for sequence diagrams, database policies, and failure boundaries.

## Quickstart (Docker Compose)

1. Copy the environment template and adjust values if deploying beyond localhost:

```bash
cp .env.example .env
```

2. Build and start PostgreSQL (`pgvector:pg16`), Redis, FastAPI, and Next.js:

```bash
docker compose up -d --build
```

3. Optionally seed the idempotent demo workspace (`acme-corp`):

```bash
docker compose exec backend python -m src.core.seed
```

Seeded demo accounts (development only):
- Admin: `admin@acme.io` / `DemoAdmin123!` (workspace slug: `acme-corp`)
- Sales Rep: `rep@acme.io` / `DemoRep123!`

Endpoints:
- Frontend UI: `http://localhost:3000`
- Backend API & Swagger UI (non-production): `http://localhost:8000/docs`
- Healthcheck: `http://localhost:8000/health`

## Local Development Setup

### Backend (`backend/`)

Requires Python 3.12+ and PostgreSQL 16 with `pgvector` (or SQLite via tests).

```bash
cd backend
python -m venv .venv
# Linux/macOS: source .venv/bin/activate
# Windows PowerShell: .\.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
alembic upgrade head
python -m src.core.seed
uvicorn src.main:app --reload --port 8000
```

### Frontend (`frontend/`)

Requires Node.js 22+.

```bash
cd frontend
npm ci
NEXT_PUBLIC_API_URL=http://localhost:8000/api/v1 npm run dev
```

## Verification & Quality Gates

### Backend Checks

```bash
cd backend
ruff check src tests
mypy src
bandit -r src -ll
pip-audit --desc on
pytest --cov=src --cov-report=term-missing --cov-fail-under=80
```

To execute the live PostgreSQL Forced RLS & `pgvector` integration test (`tests/test_postgres_rls_integration.py`) locally instead of skipping it, point `TEST_POSTGRES_URL` at an initialized Postgres instance using the non-superuser `crm_app` role:

```bash
TEST_POSTGRES_URL="postgresql+asyncpg://crm_app:crm_app_dev_pass@localhost:5432/crm_enterprise_db" pytest
```

### Frontend Checks

```bash
cd frontend
npm audit --audit-level=moderate
npm run typecheck
npm run lint
npm run test:coverage
npm run build
```

## Project Layout

```text
.
├── .github/workflows/ci.yml   # Gitleaks, Ruff/Mypy/Bandit/pip-audit/Pytest+Postgres RLS, Next/Vitest, Docker + Trivy
├── backend/
│   ├── alembic/               # Schema migrations (0001_initial_crm_schema.py)
│   ├── src/
│   │   ├── api/v1/            # auth, contacts, deals, accounts, ai_copilot, llm_credentials, mcp
│   │   ├── core/              # config, database (RLS), security (AES-GCM/bcrypt/JWT), logging, rate_limit
│   │   ├── models/            # Portable SQLAlchemy 2 models (PostgreSQL + SQLite test variants)
│   │   ├── schemas/           # Strict Pydantic v2 contracts
│   │   └── services/          # ai_service, auth_service, embedding_service, outbox_service, pipeline_service, mcp_crm_server
│   ├── tests/                 # Unit, property-based (Hypothesis), API, and Postgres RLS integration tests
│   ├── Dockerfile
│   └── pyproject.toml
├── database/
│   └── schema.sql             # Canonical DDL reference with pgvector HNSW, FORCE RLS, and crm_app grants
├── docs/
│   └── ARCHITECTURE.md
├── frontend/
│   ├── src/
│   │   ├── __tests__/         # Vitest + Testing Library + MSW integration suite
│   │   ├── app/               # App Router pages (/login, /deals, /contacts, /ai, /settings/llm-credentials)
│   │   ├── components/        # AppShell, CommandPalette, DealKanbanBoard, ContactForm, LLMCredentialsManager
│   │   └── lib/               # Typed API client with Decimal normalization & silent refresh retry
│   ├── Dockerfile
│   └── package.json
├── CHANGELOG.md
└── docker-compose.yml
```

## Known Limitations & Trade-offs

- **Offline / Deterministic Vector Embeddings**: `embedding_service.py` generates deterministic normalized 768-dimensional vectors derived via cryptographic hashing (`SHA-256` token projection) rather than calling a remote embedding endpoint on every contact write. This guarantees zero external API failures during CI, offline local development, and bulk seeding, while exercising the real PostgreSQL `pgvector` HNSW cosine operator (`<=>`). Production deployments seeking semantic synonym recall should swap `compute_deterministic_embedding()` for a batched provider call in the Outbox worker.
- **Outbox Worker Execution**: Domain events are recorded atomically in `outbox_events` and claimed via `SELECT ... FOR UPDATE SKIP LOCKED` in `outbox_service.py`, ready to be invoked by a scheduled worker or webhook dispatcher; no separate background scheduler daemon is spawned inside the web worker containers.
- **Session Persistence on Page Reload**: Access tokens are kept strictly in JavaScript memory (mitigating XSS exfiltration of bearer tokens via `localStorage`), paired with an `httpOnly` refresh cookie (`Path=/api/v1/auth`). In cross-origin local development (`localhost:3000` -> `localhost:8000`) or browsers blocking third-party cookies in production, both origin hosts should share a parent site behind a reverse proxy or BFF.
- **SQLite vs. PostgreSQL Parity in Local Runs**: When `TEST_POSTGRES_URL` is unset, `tests/test_postgres_rls_integration.py` is skipped cleanly because SQLite lacks PostgreSQL RLS and `pgvector` operators; full Forced RLS verification executes inside GitHub Actions against `pgvector/pgvector:pg16`.

## Contributing, Security & License

- Contributions: read [CONTRIBUTING.md](CONTRIBUTING.md) and the [Code of Conduct](CODE_OF_CONDUCT.md) first.
- Vulnerabilities: report them privately as described in [SECURITY.md](SECURITY.md), not in public issues.
- License: [PolyForm Noncommercial 1.0.0](LICENSE). You may use, modify, and share the code for noncommercial purposes (personal use, study, research, hobby projects, and noncommercial organizations). Commercial use requires separate permission from the maintainer. This is a source-available license, not an OSI-approved open source license, so GitHub may show it as "Other".
