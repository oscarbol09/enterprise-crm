# Changelog

All notable changes to Enterprise CRM are documented in this file following [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) conventions.

## [1.0.0] - 2026-11-20

### Security
- Enforced PostgreSQL `FORCE ROW LEVEL SECURITY` and dual `USING` + `WITH CHECK` policies across all 14 tenant-scoped tables under least-privilege `crm_app` (`NOBYPASSRLS`) role.
- Replaced invalid `SET LOCAL` interpolation with parameterized `SELECT set_config('app.current_tenant_id', :tenant_id, true)` transaction-local binding.
- Added fail-fast production hardening validation (`config.py`) rejecting default AES/JWT secrets, wildcard CORS, and offline AI stubs in `staging` and `production`.
- Replaced deprecated `passlib` with non-blocking `asyncio.to_thread` `bcrypt` hashing and added constant-time comparison helpers.
- Implemented JWT `type="access"` + `jti` claims, opaque SHA-256 refresh tokens with family rotation, and automatic family revocation on token reuse detection.
- Fixed silent exception suppression in BYOK decryption and eliminated unauthorized fallback to fake AI stubs when a live provider request fails.
- Hardened `backend/Dockerfile` (`--proxy-headers` without wildcard forwarded-allow-ips, UID `10001`), added hardened multi-stage `frontend/Dockerfile` (`nextjs` UID `10001`), and upgraded `next` to `16.4.6` / `react` to `19.3.1` / `vitest` to `5.1.1` (0 `npm audit` and `pip-audit` vulnerabilities).

### Added
- **Database & Migrations**: Added `refresh_tokens`, `lead_embeddings`, missing FK indexes, `SECURITY DEFINER` pre-auth lookup helpers, and initial Alembic migration (`0001_initial_crm_schema.py`).
- **Backend API & Services**:
  - Auth router (`/api/v1/auth/*`), Contacts CRUD + search/filter (`/api/v1/contacts`), Deals & pipeline bootstrap (`/api/v1/deals`), Accounts & Tasks (`/api/v1/accounts`, `/api/v1/tasks`), AI Copilot + `pgvector` search + HITL approval/rejection execution (`/api/v1/ai/*`), and database-backed MCP tools (`/api/v1/mcp/*`).
  - Sliding-window Redis rate limiter (`rate_limit.py`), `structlog` JSON logging with secret redaction (`logging.py`), transactional outbox worker (`outbox_service.py`), and idempotent dev seed script (`src.core.seed`).
- **Frontend**:
  - Auth context, `/login` authentication & workspace onboarding, `/ai` Copilot + semantic search + HITL proposal queue, deal creation & detail timeline modals, contact filtering & creation route handling, and real API wiring across `AppShell`.
- **Testing & CI/CD**:
  - Backend suite (`pytest`, `pytest-asyncio`, `respx`, `hypothesis`, `fakeredis`, plus `test_postgres_rls_integration.py` executed in CI against live `pgvector/pgvector:pg16`).
  - Frontend suite (`vitest`, Testing Library, `msw`) with `api-client`, `AppShell`, `DealKanbanBoard`, `CommandPalette`, `ContactForm`, and `LLMCredentialsManager` coverage.
  - Full GitHub Actions pipeline (`.github/workflows/ci.yml`) running Gitleaks, Ruff, Mypy, Bandit, `pip-audit`, Alembic + DDL checks, Pytest coverage + Postgres RLS tests, `npm audit`/lint/typecheck/Vitest/Next build, non-root UID verification, and Trivy container vulnerability scans.
  - Root `docker-compose.yml` for one-command local stack startup.

### Fixed
- Fixed `DealKanbanBoard` frozen initial state (`useState(initialDeals)`), invalid stage subset dropdowns, and missing mandatory `loss_reason` enforcement when moving deals to `Closed Lost`.
- Fixed `CommandPalette` keyboard shortcut toggling (`Ctrl/Cmd+K`) and dead 404 navigation links.
- Fixed `LLMCredentialsManager` inline revocation (replacing `window.confirm`) and removed hardcoded URLs in favor of `api-client.ts`.
- Eliminated React 19 `eslint-plugin-react-hooks` `set-state-in-effect` violations across `ContactForm`, `AppShell`, and `LLMCredentialsManager`.
