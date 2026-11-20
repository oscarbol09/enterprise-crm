# Security Policy

## Supported Versions

This project is pre-release software maintained by one person. Only the latest commit on `main` receives security fixes.

| Version | Supported |
| :--- | :---: |
| `main` (1.0.x) | Yes |
| Anything else | No |

## Reporting a Vulnerability

Please do **not** open a public issue, pull request, or discussion for a security problem.

Use GitHub's private reporting instead:

1. Go to the [Security tab](https://github.com/oscarbol09/enterprise-crm/security) of this repository.
2. Choose **Report a vulnerability**.
3. Describe the issue, the affected component, and steps to reproduce it.

If you cannot use GitHub's form, email the address listed in [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md) with the subject `SECURITY: enterprise-crm`.

Useful details to include:

- Affected file, endpoint, or SQL object (for example a table missing `FORCE ROW LEVEL SECURITY`).
- A minimal proof of concept. Do not include real customer data or real API keys.
- Your assessment of impact (cross-tenant read/write, authentication bypass, key disclosure, and so on).

### What to expect

This is a single-maintainer project, so these are targets rather than contractual SLAs:

- Acknowledgement within 5 business days.
- An initial assessment within 10 business days.
- A fix or documented mitigation for confirmed high-severity issues as soon as practical, followed by a coordinated disclosure through a GitHub Security Advisory. Reporters are credited unless they ask not to be.

## Scope

In scope:

- Tenant isolation: bypass of PostgreSQL Forced RLS, `app.current_tenant_id` handling, or the `SECURITY DEFINER` lookup functions.
- Authentication: JWT handling, refresh-token rotation and reuse detection, password hashing.
- BYOK vault: AES-256-GCM encryption of tenant LLM keys, key or plaintext leakage in logs or responses.
- AI Copilot: prompt injection that leads to unapproved writes, and bypass of the Human-in-the-Loop approval step.
- Container images and CI configuration in this repository.

Out of scope:

- Findings that require the development defaults from `.env.example` or `docker-compose.yml` to be used in production. These are documented as development-only, and `ENVIRONMENT=staging|production` refuses to start with them.
- Denial of service through volumetric traffic.
- Vulnerabilities in third-party dependencies with no demonstrable impact on this project. Report those upstream.
- Social engineering and physical attacks.

## Safe Harbor

Good-faith research that follows this policy, avoids privacy violations and service disruption, and gives time for a fix before public disclosure will not be pursued legally by the maintainer.

## Automated Checks

The repository runs Gitleaks, Bandit, `pip-audit`, `npm audit`, and Trivy in CI, and uses GitHub secret scanning with push protection and Dependabot. These reduce risk but do not replace a manual review.
