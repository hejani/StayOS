# PULSE — Real-Time Situational Awareness (StayOS Feature #2)

**Status: deployed and running in `us-east-1` (StackPrefix `pulse`).** Backend
stacks, the Triage Agent AgentCore Runtime, and the PULSE PWA at `/pulse` are
all live on the shared StayOS distribution. Redeploy with a single command (see
[Deploy](#deploy)).

PULSE is the real-time, throughout-the-day alerting layer of StayOS. It fills
the gap between LUMI's single 6:30 AM daily brief (Feature #1) and the end of a
GM's shift by pushing tiered — **CRITICAL / WARNING / INFO** — AI-triaged alerts
to the GM's device the moment a situation needs attention: walk risk, a VIP room
that isn't ready, an escalating complaint, an out-of-order room cluster, and
more.

Every CRITICAL action follows a **closed-loop "human approves, agent executes"**
pattern (EU AI Act Article 14): the agent proposes ranked options, the GM
approves one, and PULSE writes the resolving action *back* to the operational
data so the triggering condition actually clears and the originating alert
resolves as a consequence.

PULSE runs on the same StayOS origin, the same Amazon Cognito user pool, the
same AWS WAF web ACL, and the same DynamoDB operational data layer as LUMI — no
new app, no new login. It is served at **`/pulse`** on the shared StayOS
CloudFront distribution and consumes the shared `@stayos/auth` module: one login
at the shell (`/`) opens PULSE with no second sign-in (see the
[root README](../README.md) for the shell/SSO details; `/pulse/login` is a
deep-link fallback). It adds four tabs to the PWA (PULSE, VIPs, Ops, Kitchen)
plus a Web Push service worker and an AppSync Events WebSocket subscription.

## Overview

PULSE consumes item-change events from LUMI's five operational tables
(`stayos-reservations`, `stayos-rooms`, `stayos-guests`, `stayos-revenues`,
`stayos-work-orders`) via DynamoDB Streams and adds five PULSE-owned tables
(`pulse-alerts`, `pulse-rules`, `pulse-alert-history`, `pulse-push-subscriptions`,
`pulse-kitchen`). Full schemas for all tables (LUMI + PULSE) live in the
canonical [Data Model Reference](../docs/data-model.md). What is genuinely
new versus LUMI:

- an event-driven **Rule Engine**;
- an agentic **Triage Agent** (a Strands agent on Amazon Bedrock AgentCore
  Runtime backed by Claude Sonnet) that discovers and calls read-only hotel-ops
  tools over the **shared StayOS AgentCore Gateway** (MCP);
- an **Escalation Service** (GM → AGM → MOD chain plus a mandatory-GM-review
  queue);
- a **dual-channel delivery layer** (foreground realtime + background wake-up);
- a **Demo Scenario Simulator** and an **Action Executor** that together make
  the operational-data lifecycle a complete closed loop.

## Architecture

Serverless-first, CloudFormation nested stacks, Python 3.12 backend, Next.js
PWA frontend, `us-east-1`.

```
operational data change  →  Stream  →  Rule Engine  →  Alert + async Triage
        ▲                                                     │
        │                                                     ▼
   Action Executor  ◀──  GM approves ranked option  ◀──  Dual-channel push
   (write-back)
        │
        └──►  change clears the condition  →  Stream  →  Rule Engine
                                                            re-evaluates →
                                                            originating alert
                                                            → RESOLVED
```

The end-to-end path:

1. **Rule Engine (`pulse-rule-evaluator`).** A DynamoDB Streams event source
   mapping on each operational table drives a thin handler that delegates to
   pure `evaluate_rules(...)` logic. Rule definitions are loaded per property
   from `pulse-rules` (cached, ≤60 s TTL) and evaluated against a small, safe,
   declarative trigger model (never `eval`-ed). Matched rules produce Alert
   records with `status = UNACKNOWLEDGED`.
2. **Triage Agent (`pulse-triage-agent` on AgentCore Runtime).** For a
   CRITICAL/WARNING alert with `agentTriageEnabled`, the Rule Engine invokes the
   agent **asynchronously** (`bedrock-agentcore:InvokeAgentRuntime`,
   fire-and-forget) so delivery is never blocked. The agent gathers facts by
   calling read-only tools over the **shared StayOS AgentCore Gateway** (the
   same Gateway LUMI's chat agent uses, with PULSE-specific tools added to the
   same target), produces a schema-validated `triageBrief` (summary, integer
   confidence, 2–5 ranked options, at most one recommended), attaches it, and
   publishes an `ALERT_UPDATED` event. INFO alerts skip triage.
3. **Escalation Service (`pulse-escalation-service`).** Evaluates the escalation
   trigger hierarchy (records every matching reason as a set) and runs the
   time-based GM → AGM → MOD chain via EventBridge Scheduler one-shot
   checkpoints.
4. **Dual-channel delivery (`pulse-push-service`, `pulse-info-batcher`).**
   - **AWS AppSync Events** — foreground / in-app realtime. Open PWA clients
     subscribe over WebSocket to their property channel and receive alert
     create / status-change / resolve events instantly (fully managed; no
     connection table to operate).
   - **Web Push (VAPID)** — background wake-up for a closed or backgrounded app
     (the CRITICAL ≤30 s / WARNING ≤120 s notification). INFO alerts are batched.
5. **Closed-loop Action Executor (`pulse-action-executor`).** On an approved
   option it performs the write-back mutation that clears the triggering
   condition **and** sets the originating alert to `RESOLVED` in a single
   `TransactWriteItems`, then publishes the RESOLVED change to AppSync Events so
   open apps move the card to resolved history instantly. The write-back
   re-enters through Streams; the Rule Engine sees the condition no longer holds
   and — correlating by `sourceEntityRef` / `dedupeKey` — emits no duplicate.
6. **Demo Scenario Simulator (`pulse-demo-simulator`).** Scripted, deterministic
   mutations to the operational tables that stand in for a live PMS/SPOG feed and
   trigger the demo scenarios on cue. Gated by `EnableDemoSimulator`.
7. **VIPs / Ops facade (`pulse-ops-read`).** The C3b read facade backing
   `GET /vips` and `GET /ops`; an MCP client that reads live hotel-ops data
   through the shared Gateway and shapes it for the VIPs and Ops tabs.

## Project structure

```
pulse/
├── backend/                     # Python 3.12, src layout
│   ├── pyproject.toml           # deps + ruff/black/pytest config
│   ├── src/pulse/
│   │   ├── api/                 # pulse-api Lambda: router, alerts, lifecycle,
│   │   │                        #   approvals, rules admin, subscriptions
│   │   ├── rule_engine/         # stream-driven rule evaluation + validation
│   │   ├── triage/              # brief validation + structural specializations
│   │   ├── escalation/          # trigger hierarchy + time-based chain
│   │   ├── delivery/            # realtime publish + Web Push
│   │   ├── action_executor/     # approved-action write-back + transactional resolve
│   │   ├── demo_simulator/      # deterministic scenario mutations
│   │   ├── ops_read/            # pulse-ops-read facade: /vips, /ops via Gateway MCP
│   │   ├── history/             # shift-handover window query
│   │   ├── observability/       # metrics/log helpers
│   │   └── common/              # models, config, dynamo, logging, errors
│   ├── services/triage-agent/   # containerized Strands agent for AgentCore Runtime
│   └── tests/                   # pytest unit + property-based tests
├── frontend/                    # Next.js PWA (PULSE/VIPs/Ops/Kitchen tabs)
└── infrastructure/
    ├── root-stack.yaml          # pulse-root
    └── nested-stacks/
        ├── pulse-data.yaml          # tables, GSIs, TTL, streams
        ├── pulse-pipeline.yaml      # rule evaluator, executor, simulator, schedules
        ├── pulse-api.yaml           # API GW, pulse-api, pulse-ops-read, AppSync Events
        └── pulse-observability.yaml # dashboard, alarms, metric filters, X-Ray
```

## Build & test

Backend (from `pulse/backend/`):

```bash
pip install -e '.[dev]'     # install runtime + dev dependencies
pytest                       # unit + property-based tests
ruff check src tests         # lint (PEP 8, isort, pydocstyle Google convention)
black --check src tests      # formatting check
```

Frontend (from `pulse/frontend/`):

```bash
npm install
npm run lint                 # next lint / eslint
npm run build                # next build (static export to out/)
npm run test:run             # vitest (unit) + fast-check (property) once
```

Infrastructure (from `pulse/infrastructure/`):

```bash
cfn-lint root-stack.yaml nested-stacks/*.yaml
```

## Deploy

> **Deploying the whole platform?** Use the repo root: `make deploy-all`
> (LUMI + PULSE) then `make shell-deploy`. See the
> [root README](../README.md#deployment). PULSE cannot be deployed standalone
> from a clean account — it needs values produced by the LUMI deploy (Cognito
> pool, the five operational-table stream ARNs, the shared Gateway endpoint, the
> Tool Lambda ARN), which `make deploy-all` captures and threads in
> automatically.

PULSE is already deployed. This section covers **PULSE-only** redeploys and
internals.

`make deploy-all` deploys LUMI, then the PULSE stack, registers the shared
Gateway tools, builds + deploys the Triage Agent to AgentCore Runtime
(re-deploying the stack with its runtime ARN), and publishes the PULSE PWA to
`/pulse`. Container builds run remotely on CodeBuild (ARM64); AWS Finch is the
sanctioned tool for any local container work.

**PULSE-only targets** (LUMI must already be deployed):

```bash
make pulse-deploy PROFILE=... REGION=...        # redeploy the PULSE stack (needs LUMI-derived vars)
make pulse-triage-deploy PROFILE=... REGION=... # rebuild + redeploy the Triage Agent container
make pulse-gateway-deploy ...                   # (re)register PULSE Gateway tools
make pulse-deploy-frontend ...                  # rebuild + publish the PULSE PWA to /pulse
```

A standalone stack deploy uses `aws cloudformation deploy` from
`pulse/infrastructure/`, nested stacks in dependency order:

```
pulse-root  →  pulse-data  →  pulse-pipeline  →  pulse-api  →  pulse-observability
```

### Prerequisites (handled automatically by `make deploy-all`)

1. **MCP dependencies bundled** — the `[ops-read]` optional-dependency group
   (`strands-agents`, `mcp-proxy-for-aws`) is installed into the shared Lambda
   package by `make package-backend`, so `pulse-ops-read` can act as an MCP
   client to the Gateway.
2. **LUMI's shared data stack** has `StreamViewType = NEW_AND_OLD_IMAGES` on the
   five operational tables and exports their stream ARNs. Additive — it does not
   change LUMI's read paths, item schemas, or read IAM.
3. **PULSE Gateway tools registered** via `make gateway-deploy` (adds
   sister-property availability, walkable-guest selection, and room-move
   candidate tools to the shared StayOS AgentCore Gateway target).
4. **Triage Agent container** built via CodeBuild (ARM64 image on AgentCore
   Runtime, mirroring the LUMI chat agent), runtime ARN written to SSM at
   `/pulse/triage/runtime-arn` and threaded back into the stack.

### Parameters to thread through the stacks

`UserPoolClientId`, the operational-table ARNs/names, the five operational
stream ARNs, `GatewayEndpointUrl` (SSM `/pulse/gateway/endpoint-url`), and
`VapidPublicKey`. Set `EnableDemoSimulator` to `false` for a non-demo
deployment (the simulator and the `/demo/*` routes then behave as if absent).

## Links

- REST API spec: [`../openapi.yaml`](../openapi.yaml) — the StayOS root OpenAPI
  spec, which currently documents the PULSE real-time alerts API.
- Spec (requirements / design / tasks):
  [`.kiro/specs/initial-pulse-project/`](.kiro/specs/initial-pulse-project/)
- Interactive prototype:
  [`aiplc-docs/04-prototypes/pulse-prototype.html`](aiplc-docs/04-prototypes/pulse-prototype.html)
- AI-PLC discovery trail: [`aiplc-docs/`](aiplc-docs/)
