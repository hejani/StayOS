# StayOS — Agent Guide (repo root)

eiifcbnctvhtknjltdledjrrcgivgnukeviecgiihdeh


This file holds the rules that apply everywhere. Each feature's `AGENTS.md`
adds only feature-specific detail and assumes these rules.

## Repository layout

- `stayos-shell/` — the StayOS shell: unified login + feature launcher, served at the site root `/`. A GM signs in here once; both features trust the shared session (SSO). Built and tested; deploy is manual.
- `lumi/` — Feature 1 (LUMI): daily AI-generated GM brief + voice/chat agents. Served at `/lumi`. Built and deployed.
- `pulse/` — Feature 2 (PULSE): real-time tiered AI-triaged alerts with closed-loop resolution. Served at `/pulse`. Built and tested; deploy is manual.
- `shared/` — cross-feature layer. `shared/auth/` is the shared StayOS auth module (`@stayos/auth`), consumed by the shell, LUMI, and PULSE (see `shared/README.md`). The shared *infrastructure* carve-out (Cognito/WAF) is still deferred until its own second consumer.

All three frontends are static-export Next.js apps served from ONE shared CloudFront distribution + S3 bucket: the shell at `/`, LUMI at `/lumi`, PULSE at `/pulse`. They share one Cognito user pool, one WAF web ACL, one DynamoDB operational layer, and — via `shared/auth/` on the single origin — one browser session.

## Golden rules (safety + workflow)

- Scope every change to ONE feature. A change under `lumi/` should not touch `pulse/` or `shared/`, and vice versa.
- Do NOT modify another feature's files. There are two sanctioned cross-feature exceptions, both to be treated as additive/shared: (1) the shared StayOS AgentCore Gateway tool layer in `lumi/backend/functions/tools/` + `lumi/backend/tools/tool-schema.json`, which PULSE agents also consume; (2) the shared auth module in `shared/auth/` (`@stayos/auth`), consumed by the shell, LUMI, and PULSE. A change that deliberately spans the shell + both features (e.g. a coordinated auth change) is allowed, but call it out explicitly.
- Prefer moving code into `shared/` once a second consumer actually needs it rather than speculatively, but treat this as a guideline rather than a hard gate. `shared/auth/` is the clearest example (three consumers); the shared *infrastructure* carve-out can move here when it makes sense.
- Prefer staging specific files over `git add -A`. Use imperative-mood commit messages and `kebab-case` branch names (`feature/...`, `fix/...`).
- Run the relevant build/tests before claiming a task is done.

## Cross-cutting conventions

### Runtime / stack

- Backend: Python 3.12 (boto3 + AWS Lambda Powertools). Serverless-first.
- Frontend: Next.js (App Router) + React + Tailwind, static-export PWA.
- IaC: **CloudFormation nested stacks — NOT CDK, NOT SAM** — deployed via `aws cloudformation deploy`.
- Container builds: **AWS Finch (`finch`), not Docker** (agent containers build remotely on CodeBuild ARM64).
- Region: `us-east-1`.

### PYQUALITY (Python)

- Complete type hints including return types (`-> None` where nothing is returned).
- Specific exceptions only — never bare `except:`; prefer typed boto3 `client.exceptions.*` over string-matching error codes.
- Structured logging via Powertools `Logger` — no `print()`.
- Google-style docstrings on modules, classes, and public functions.
- PEP 8 + f-strings.
- Thin `lambda_handler` that parses the event and delegates to unit-testable business logic.
- boto3 clients created at module level with an explicit retry `Config`; use paginators/waiters, not manual loops.
- Resource names come from environment variables — never hardcoded.

### NAMING

- Resources carry the `stayos` project-name prefix. Use a `StackPrefix` of `stayos-<feature>` (e.g. `stayos-lumi`, `stayos-pulse`) propagated to all resource names.
- Physical names kebab-case: `${StackPrefix}-<purpose>`. CloudFormation logical IDs PascalCase.
- Python: `snake_case` files/functions/vars, `UPPER_SNAKE` constants, handler always named `lambda_handler`.
- DynamoDB attributes `camelCase`. React components PascalCase; TS utils camelCase; no `I` interface prefix.
- API routes: kebab-case plural nouns, no verbs.
- Every AWS resource tagged `Project` + `resilience-tier`; IAM role names include `${AWS::Region}`.
- Do NOT use em dashes in AWS resource names or descriptions — use hyphens.

### Testing

- Property-based tests where logic is universally quantified: Hypothesis (Python), fast-check (TS).
- One test per documented design Property, tagged `# Feature: <spec>, Property N: ...`.
- Mock external boundaries (Bedrock, DynamoDB, AppSync, Web Push) in unit + property tests.

## How to work per feature

Work from inside the feature directory and use that feature's Makefile/tests.
The root `Makefile` only delegates: `make lumi-<target>` runs `make -C lumi <target>`, `make pulse-<target>` runs `make -C pulse <target>`.

```bash
# StayOS shell (login + launcher, served at /)
cd stayos-shell && make test  # frontend only
# LUMI
cd lumi && make test          # backend + frontend
# PULSE
cd pulse && make test         # backend + frontend
# Shared auth module
cd shared/auth && npm test    # vitest (unit + fast-check SSO property)
```

Generic backend test command (note `python3`, not `python`):

```bash
cd <feature>/backend && python3 -m pytest
```

## Where to look first

- `llms.txt` (repo-root index for the whole repo) and each feature's `README.md`.
- Each feature `README.md` for prerequisites and deploy steps.
- The root `Makefile` for how to build/test/deploy each feature (it delegates to `make -C <feature> <target>`).
- `openapi.yaml` (repo root) for the REST API surface.
- `docs/data-model.md` for the canonical platform-wide data model (LUMI + PULSE table schemas, keys/GSIs, enumerated values, relationships, seed volumes).
- Each feature's `AGENTS.md` for feature-specific rules on top of this root guide.
- `CONTRIBUTING.md` for PR scoping, `shared/README.md` for the shared-layer boundary.
