# Changelog

All notable changes to Enterprise CRM are documented in this file following [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) conventions.

## [Unreleased]

### Added
- **B2B Data Architecture & RBAC**: Added `company_affiliations`, `deal_participants` (buying committee), SCD Type 2 `deal_stage_history`, `custom_field_definitions` JSONB registry with GIN indexes, RFC 5322 `synced_email_messages` idempotent sync ledger, `entity_audit_logs`, hierarchical `team_id` RBAC (`rbac_service.py`), cursor-paginated roll-up timelines, and non-destructive entity merges (`0002_b2b_graph_fx_and_analytics.py`).
- **Operational Pipeline & Directory UI**: Added high-density `DealDataGrid` with inline amount/stage editing and footer aggregations, slide-over `DealPeekDrawer` with Omnibox slash commands (`/call`, `/note`, `/meeting`, `/task`), native HTML5 Drag-and-Drop in `DealKanbanBoard`, single-key shortcuts (`C`, `D`, `/`), email-domain auto-inference in `ContactForm`, and dedicated `/accounts` and `/tasks` workspaces.
- **Multi-Currency FX, Merge Redirects & Task Hygiene**: Added `Decimal` multi-currency normalization (`exchange_rate_to_usd`, `normalized_amount_usd`) with immutable FX locking on deal close (`409 Conflict`), transparent `merged_into_id` redirect resolution, `POST /contacts/{id}/restore` undo soft-delete, `POST /accounts/{id}/merge`, automatic stale task cancellation on deal close + `POST /tasks/prune-zombies`, stage-gated `min_stage_position` custom field validation rejecting placeholder strings, and `GET /deals/{id}/playbook`.
- **Design System & Typography Refresh**: Adopted `IBM Plex Sans` + `IBM Plex Mono`, a warm Stone & Pine light/dark palette with sidebar theme toggle, themed browser primitives (`::selection`, `caret-color`, `prefers-reduced-motion`), 6px/8px component radii, plain-language operational copy, and automated design-system regression checks (`design-system-guardrails.test.tsx`).
- **Revenue Analytics, Attribution & CSV Data Transfer**: Added `/api/v1/analytics/forecast`, `/funnel`, `/attribution`, `/snapshots`, `/waterfall`, and `/win-loss` endpoints with exact `Decimal` USD normalization, Sales Velocity, Pipeline Coverage Ratio, bidirectional engagement health (`last_inbound_activity_at` vs `last_outbound_activity_at` Ghosting Risk detection), Pipeline Waterfall Bridge (`pipeline_snapshots`), structured Win/Loss Matrix (`loss_category`, `competitor_name`, `missing_feature_tag`), and `source_channel` revenue attribution; added Bundled CSV Importer (`/api/v1/data/contacts/import`) creating accounts, contacts, and deals with automatic HubSpot/Salesforce header mapping, Dry-Run preview, deduplication, quarantine reporting, and atomic 1-click batch rollback (`POST /api/v1/data/imports/{batch_id}/rollback` via `import_batches`), plus formula-sanitized CSV exports (`/api/v1/data/export/{entity}`).
- **Keyboard Flow & Inline Stage-Gate UX**: Added `X-Stage-Gate-Fields` header metadata on HTTP `422` stage-gate rejections driving an inline 1-field popover in `DealKanbanBoard` with auto-retry on save, structured Closed-Lost taxonomy inputs, `j`/`k`/`ArrowDown`/`ArrowUp` + `Space`/`Enter` keyboard row navigation in `DealDataGrid`, cursor pagination (`X-Next-Cursor`) on master listings, live `Cmd+K` contact/deal search, debounced server-side contact filtering, and stale-deal badges (`>14d`) on Kanban cards.
- Community and governance files: `LICENSE` (PolyForm Noncommercial 1.0.0), `SECURITY.md`, `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md` (Contributor Covenant 2.1), issue and pull request templates, `CODEOWNERS`, and Dependabot configuration.
- AI provider models are configurable through the `GEMINI_MODEL`, `ANTHROPIC_MODEL`, and `OPENAI_MODEL` environment settings.

### Fixed
- AI Copilot parsing now accepts fenced JSON surrounded by provider commentary while preserving strict response-schema validation.

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
