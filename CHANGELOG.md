# Changelog

All notable changes to **StayOS** are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project aims to follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.1.0] - 2026-09-04

Platform reliability and reach: adds the shared Unified Data Orchestrator so the
demo dataset stays current on its own, a public marketing landing page for the
StayOS shell, and a set of correctness and security fixes. No breaking changes.

### Added
- **Unified Data Orchestrator** (`shared/data-orchestrator/`, `StackPrefix`
  `stayos-data`) — a Step Functions state machine (Quiesce → Generate →
  Reconcile → UnQuiesce → RegenerateBrief → PrimeBaseline) plus one per-property
  EventBridge Scheduler rule that re-anchors the deterministic 30-day window at
  each property's local midnight via idempotent upsert (pausing PULSE evaluation
  during the rewrite so no alert storm fires), then regenerates that day's brief.
  It is additive and never bulk-rewrites or re-seeds the live tables.
- **Prime-on-deploy** — the orchestrator deploy step primes today's data for
  every pilot property (idempotent, failure-isolated), so each GM has a current
  daily brief immediately after `make deploy-all` with no manual step.
- **StayOS marketing landing page** — a public landing page at the shell root
  (`/`) that explains StayOS and its two live features (LUMI and PULSE) before
  sign-in; a Sign In call-to-action reveals the login form, and authenticated
  visitors still land on the feature launcher grid (SSO preserved).

### Changed
- `make deploy-all` now also deploys the shared Data Orchestrator, wired to the
  live LUMI table names and PULSE rule-evaluator stream mappings.
- Shortened PULSE CloudFormation stack descriptions to under 25 words.

### Fixed
- **VIP arrivals** — `get_vip_guests` now falls back to a live reservations
  query when a brief for the current date is missing, so it never reports a
  false "no VIP arrivals"; the fallback is deduped and capped to match the brief.
- **PULSE triage** — fixed an out-of-order (OOO) `triageBrief` placeholder leak
  by threading the real block id.
- **LUMI voice agent** — corrected `get_revenue` parameter names to match the
  tool schema.

### Security
- Merged security fixes (dependency bumps and verified secret-scan allowlists).
- Removed a real AWS account ID from `docs/data-model.md` and stopped tracking
  local working-notes docs.

## [1.0.0] - 2026-08-21

Initial version 1 — the StayOS reference implementation (prototype / customer
demo): the operating system for hotel General Managers. Two live features on one
shared platform (unified login shell, one Amazon Cognito pool, one CloudFront
origin, one AWS WAF, one shared DynamoDB operational data layer), serverless-first
on AWS (`us-east-1`).

### Platform
- **StayOS shell** — unified login + feature launcher served at the site root
  `/`. A GM signs in once and both features trust the shared session (SSO) via
  the shared `@stayos/auth` module (`stayos.*` `localStorage` on the shared
  origin). Includes a StayOS logo mark/lockup and a first-login onboarding tour
  (LUMI → PULSE coachmark) plus a manual "Take a tour" replay.
- **Shared data layer** — 5 read-only operational dataset tables + 2 LUMI
  application tables (`stayos-*`), seeded with ~24k items of deterministic hotel
  operations data across 5 pilot properties; `NEW_AND_OLD_IMAGES` DynamoDB
  Streams feed PULSE. See [`docs/data-model.md`](docs/data-model.md).
- **Shared StayOS AgentCore Gateway** — one MCP tool layer (read-only hotel-ops
  tools) consumed by both LUMI's chat agent and PULSE's triage agent.
- **Root `make deploy-all`** — one-command platform deploy: LUMI, then PULSE
  wired to LUMI's outputs (Cognito, stream ARNs, Gateway endpoint, Tool Lambda),
  Gateway tool registration, Triage Agent build, and PULSE PWA publish.

### LUMI (Feature 1) — Daily GM Intelligence Brief
- Daily AI-generated brief (KPIs, VIP arrivals, overbooking/walk risk, OOO rooms)
  as a mobile dashboard plus a 60–90s Amazon Polly audio brief (multi-language).
- **Voice agent** (Amazon Nova Sonic, WebSocket push-to-talk) and **chat agent**
  (Strands + Claude Sonnet via the shared Gateway over MCP) for Q&A over the same
  dataset, both on Amazon Bedrock AgentCore Runtime.
- Brief history, per-GM EventBridge Scheduler delivery, AWS WAF, CloudWatch/X-Ray
  observability. Served at `/lumi`.

### PULSE (Feature 2) — Real-Time Situational Awareness
- Event-driven **Rule Engine** over the operational-table streams producing
  tiered alerts (CRITICAL / WARNING / INFO).
- Agentic **Triage Agent** (Strands + Claude Sonnet on AgentCore Runtime, shared
  Gateway) that attaches a schema-validated `triageBrief` (summary, confidence,
  ranked options) asynchronously.
- **Escalation Service** (GM → AGM → MOD chain), **dual-channel delivery**
  (AppSync Events realtime + Web Push), and a **closed-loop Action Executor**
  ("human approves, agent executes", EU AI Act Article 14) that writes the
  resolving action back and resolves the originating alert.
- PWA tabs (PULSE / VIPs / Ops / Kitchen), a demo scenario simulator, a
  30-minute alert auto-resolve sweeper, and 4 CloudFormation nested stacks.
  Served at `/pulse`.

[1.1.0]: https://github.com/hejani/StayOS/releases/tag/v1.1.0
[1.0.0]: https://github.com/hejani/StayOS/releases/tag/v1.0
