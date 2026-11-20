# Contributing

Thanks for taking the time to contribute. This guide explains how to get a change merged with as little back and forth as possible.

By participating you agree to follow the [Code of Conduct](CODE_OF_CONDUCT.md). Security problems go through [SECURITY.md](SECURITY.md), never through public issues.

## Licensing of Contributions

The project is released under the [PolyForm Noncommercial License 1.0.0](LICENSE). By opening a pull request you confirm that you wrote the change (or have the right to submit it) and that it may be distributed under that license. The maintainer may also offer the project, including your contribution, under separate commercial terms.

If that is not acceptable to you, please do not submit code.

## Before You Start

- Search existing issues and pull requests first.
- For anything larger than a small fix, open an issue and describe the problem before writing code. This avoids work on changes that do not fit the project direction.
- Good first contributions: tests for uncovered branches (see the coverage report), documentation fixes, accessibility improvements in the frontend.

## Development Setup

Requirements: Python 3.12+, Node.js 22+, and optionally Docker with PostgreSQL 16 + `pgvector` for the full integration test.

```bash
# Backend
cd backend
python -m venv .venv
# Windows: .\.venv\Scripts\Activate.ps1   |  Linux/macOS: source .venv/bin/activate
pip install -r requirements-dev.txt

# Frontend
cd ../frontend
npm ci
```

The full stack can also be started with `docker compose up -d --build` (see the README).

## Checks That Must Pass

CI runs the same commands. Run them locally before pushing.

Backend (`backend/`):

```bash
ruff check src tests
mypy src
bandit -r src -ll
pip-audit --desc on
pytest --cov=src --cov-report=term-missing --cov-fail-under=80
```

Frontend (`frontend/`):

```bash
npm audit --audit-level=moderate
npm run typecheck
npm run lint
npm run test:coverage
npm run build
```

Without `TEST_POSTGRES_URL`, `tests/test_postgres_rls_integration.py` is skipped locally and only runs in CI. If you touch `database/schema.sql`, migrations, or anything that relies on RLS, run it against a real PostgreSQL 16 instance with the `crm_app` role (see the README) instead of relying on the skip.

## Project Rules

These are the rules reviewers will check:

1. **Tenant isolation is not optional.** Every new tenant-owned table needs `tenant_id`, `ENABLE` and `FORCE ROW LEVEL SECURITY`, and a policy with both `USING` and `WITH CHECK`. Update `database/schema.sql` and add an Alembic migration; keep them in sync.
2. **No network I/O inside a database transaction.** Read, close the session, call the external service, then open a short write session (see `ai_copilot.py`).
3. **AI never writes directly.** Model output becomes an `ai_proposals` row. Only an explicit approval executes the change.
4. **No silent failures.** No empty `except`, no swallowed errors, no fallback that fakes a successful result. Log with context or propagate.
5. **No secrets in code, tests, logs, or screenshots.** Test keys must be obviously fake.
6. **Tests with the change.** Bug fixes need a test that fails without the fix. Aim to keep backend branch coverage at or above 80%.
7. **Keep the diff small and focused.** Do not mix refactors, formatting changes, and behaviour changes in one pull request.
8. **Documentation matches reality.** If behaviour changes, update `README.md`, `docs/ARCHITECTURE.md`, and `CHANGELOG.md` in the same pull request. Do not document features that do not exist.

## Commit Messages

Use [Conventional Commits](https://www.conventionalcommits.org/) in English, and explain **why** in the body when it is not obvious.

```text
fix(auth): revoke token family when a refresh token is replayed

A replayed token means the family may be compromised; revoking only the
presented token left the attacker's rotated token usable.
```

Common types: `feat`, `fix`, `test`, `docs`, `ci`, `refactor`, `chore`. Scopes used so far: `db`, `backend`, `frontend`, `docker`, `repo`.

## Pull Requests

1. Fork the repository and create a branch from `main` (`feat/short-description` or `fix/short-description`).
2. Make the change, with tests and docs.
3. Run the checks above.
4. Open a pull request using the template. Link the issue it closes.
5. Respond to review comments by pushing new commits. Maintainers may squash on merge.

Pull requests that fail CI will not be reviewed until they are green. Do not force-push over review history without saying so.

## Reporting Bugs and Requesting Features

Use the issue templates. A good bug report has the exact steps, expected versus actual behaviour, versions (OS, Python, Node, browser), and logs with secrets removed. A good feature request describes the problem first and the proposed solution second.

## Response Times

This is maintained by one person in spare time. Expect a first reply within about a week. A slow reply is not a rejection.
