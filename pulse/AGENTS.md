# PULSE — Agent Guide (StayOS Feature 2)

PULSE is the real-time, throughout-the-day alerting layer: tiered
(CRITICAL / WARNING / INFO) AI-triaged alerts pushed to the GM's device the
moment a situation needs attention, with a closed-loop "human approves, agent
executes" resolution path (EU AI Act Article 14). **Deployed and running in
`us-east-1`** (root stack `pulse-us-east-1` + nested stacks, the Triage Agent
AgentCore Runtime, and the `/pulse` PWA are all live).

The root [`../AGENTS.md`](../AGENTS.md) applies in full (safety rules,
PYQUALITY, NAMING, testing, runtime/stack). This file adds only PULSE
specifics. `StackPrefix = pulse`, region `us-east-1`. PULSE reuses LUMI's PWA
shell origin, Cognito user pool, WAF web ACL, DynamoDB operational tables, and
the shared StayOS AgentCore Gateway — no new app, no new login. It is served at
**`/pulse`** on the shared StayOS CloudFront distribution; the StayOS shell owns
the site root `/` (unified login + feature launcher) and LUMI owns `/lumi`.
PULSE consumes the shared `@stayos/auth` module (from `shared/auth/`) via a
build-time path alias, trusts the shared browser session (single sign-on), and
redirects unauthenticated users to the shell at `/`. `src/lib/auth.ts` is a thin
adapter over `@stayos/auth`; `/pulse/login` is a deep-link fallback only.

## Structure

- `backend/src/pulse/` (Python 3.12, src layout) sub-packages:
  `api` (pulse-api Lambda: alerts, lifecycle, approvals, rules admin, subscriptions),
  `rule_engine` (stream-driven evaluation + validation),
  `triage` (brief validation + structural `specializations`),
  `escalation` (trigger hierarchy + time-based GM→AGM→MOD chain),
  `delivery` (realtime publish + Web Push),
  `action_executor` (approved-action write-back + transactional resolve),
  `demo_simulator` (deterministic scenario mutations),
  `ops_read` (pulse-ops-read facade for `/vips`, `/ops` via Gateway MCP),
  `history` (shift-handover window query),
  `observability`, `common` (models, config, dynamo, logging, errors).
- `backend/services/triage-agent/` — containerized Strands agent for AgentCore Runtime (ARM64, mirrors the LUMI chat agent).
- `frontend/` — Next.js PWA adding four tabs (PULSE, VIPs, Ops, Kitchen) + Web Push service worker + AppSync Events subscription.
- `infrastructure/nested-stacks/` — `pulse-data`, `pulse-pipeline`, `pulse-api`, `pulse-observability` under `root-stack.yaml` (`pulse-root`).

## Commands

```bash
# Full deploy (root -> data -> pipeline -> api -> observability, in order).
# Guards required params (Cognito user pool + 5 LUMI stream ARNs) - no template default.
make deploy

# Package only (build + upload the shared Lambda zip, package nested templates)
make package               # = package-backend + package-infra
make validate              # cfn-lint the root + nested CloudFormation templates

# AgentCore + Gateway (out-of-band, CodeBuild ARM64 - no CFN resource type)
make gateway-deploy        # register PULSE tools on the shared StayOS Gateway target
make triage-deploy         # build + deploy the Triage Agent container to AgentCore Runtime

# Tests + lint (run before claiming done)
make test                  # backend pytest + frontend vitest
make test-backend          # backend pytest (unit + Hypothesis property tests)
make test-frontend         # frontend vitest (unit + fast-check), once
make lint                  # ruff (backend) + next lint / eslint (frontend)
make build-frontend        # Next.js static export to out/

make clean                 # remove build artifacts
```

Run `make help` from `pulse/` for the full target list. The targets wrap the
raw tooling — backend `pip install -e '.[dev]'` + `python3 -m pytest` + `ruff`,
frontend `npm install` + `vitest`, infra `cfn-lint` + `aws cloudformation
deploy`. Container builds run remotely on **CodeBuild (ARM64 Graviton)** — no
local Docker required; use `finch` if you need a local container. PULSE is
deployed in `us-east-1`; redeploy with `make deploy-all` from the repo root (or
the per-step targets above). The triage runtime ARN is tracked in SSM
(`/pulse/triage/runtime-arn`), not in CloudFormation.

## Key invariants (preserve these — from design.md Decisions + Properties)

- **Triage is an async agentic call (Decisions 7, 8).** The rule engine delivers the alert first, then invokes the Triage Agent on **AgentCore Runtime** (`bedrock-agentcore:InvokeAgentRuntime`, fire-and-forget); the agent attaches the brief and publishes `ALERT_UPDATED`. Do NOT reintroduce a synchronous triage Lambda or block delivery on the brief.
- **Triage uses the shared StayOS Gateway (MCP)** for facts. Fact-gathering is deterministic; structural guarantees come from `pulse.triage.specializations` + `pulse.triage.validation` (Property 18). Keep that pure logic reusable by the runtime service — do not move guarantees into the model output.
- **Closed loop (Decision 6; Properties 26, 27).** The Action Executor does the operational write-back AND the transactional RESOLVED in one `TransactWriteItems`. Re-evaluation must never create a duplicate: correlate by `sourceEntityRef` / `dedupeKey`; RESOLVED is terminal. Loop safety depends on what the data now says (condition cleared) + alert correlation, never on who wrote.
- **Article 14 gate (Property 7).** No CRITICAL ranked-option action executes without a recorded GM approval. No write-back before that approval.
- **Property scoping is enforced server-side everywhere (Properties 25, 28)** — including the AppSync Events OnSubscribe handler (reject/narrow channels to the caller's property set; per-user channel requires own-identity match).
- **Realtime publish is best-effort / non-blocking** — it must never fail the originating operation (alert create, status change, resolve).
- **Auth is the shared `@stayos/auth` module, not a PULSE copy.** The session lives in `localStorage` (`stayos.*`) on the shared origin so it is common to the shell, LUMI, and PULSE (SSO). Do NOT reintroduce a PULSE-local auth implementation or a per-app `sessionStorage` session. Unauthenticated / session-lost redirects go to the shell root `/` (raw, not `withBase` — `/` is outside PULSE's `/pulse` basePath); `withBase()` is still used for in-app PULSE paths (service worker, in-app links).
- Do NOT use em dashes in AWS resource names or descriptions.

## Testing

- Backend: Hypothesis property tests; frontend: fast-check. One test per documented design Property, tagged `# Feature: initial-pulse-project, Property N: ...`.
- Mock external boundaries (Bedrock, DynamoDB, AppSync Events, Web Push).

## Progress tracking

- `.kiro/specs/initial-pulse-project/tasks.md` is the live checklist — keep checkboxes current as tasks complete.
- All tasks complete, including Task 25 (deploy): PULSE is deployed and running in `us-east-1`.

See `README.md`, the spec under `.kiro/specs/initial-pulse-project/`
(requirements / design / tasks), and `aiplc-docs/` for discovery context.
