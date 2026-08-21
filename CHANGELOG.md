# Changelog

All notable changes to **StayOS** are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project aims to follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
  Streams feed PULSE. See [`lumi/docs/data-model.md`](lumi/docs/data-model.md).
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

[1.0.0]: https://github.com/hejani/StayOS/releases/tag/v1.0
