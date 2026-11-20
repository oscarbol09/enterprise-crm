## What and why

<!-- What does this change do, and why is it needed? Link the issue: Closes #123 -->

## Type of change

- [ ] Bug fix
- [ ] New feature
- [ ] Refactor (no behaviour change)
- [ ] Tests only
- [ ] Documentation only
- [ ] CI / Docker / tooling

## Checklist

- [ ] I read [CONTRIBUTING.md](../CONTRIBUTING.md) and agree my contribution is licensed under the project license.
- [ ] Backend: `ruff`, `mypy`, `bandit`, `pip-audit`, and `pytest --cov` pass locally (if backend changed).
- [ ] Frontend: `typecheck`, `lint`, `test:coverage`, and `build` pass locally (if frontend changed).
- [ ] Tests added or updated; a bug fix includes a test that fails without it.
- [ ] New tenant tables have `FORCE ROW LEVEL SECURITY` plus `USING` and `WITH CHECK`, in both `schema.sql` and an Alembic migration.
- [ ] No network I/O inside DB transactions; no AI-driven write without human approval.
- [ ] No secrets, real keys, or personal data in code, tests, or logs.
- [ ] `README.md`, `docs/ARCHITECTURE.md`, and `CHANGELOG.md` updated if behaviour changed.

## How I tested this

<!-- Commands run, manual steps, screenshots for UI changes. -->
