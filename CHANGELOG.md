# Changelog

All notable changes to **StayOS** are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project aims to follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

> This changelog is derived from the git commit and merge history. `v1.4` is the
> only release tag to date and points at the monorepo restructure (`76cd219`).
> Dates below reflect when each milestone was merged into `main`.

## [Unreleased]

On branch `feat/pulse` (not yet merged into `main`). Brings the **PULSE** feature
from planning-only to a built, tested feature and wires the two-feature deploy.

### Added
- **PULSE** feature (StayOS Feature #2): real-time tiered GM alerting
  (CRITICAL/WARNING/INFO) with agentic "human approves, agent executes" triage —
  DynamoDB Streams on LUMI's operational tables → rule evaluator → Strands triage
  agent on Bedrock AgentCore Runtime (via the shared StayOS Gateway) → alerts,
  plus escalation (EventBridge Scheduler), dual-channel delivery (AppSync Events +
  Web Push), and a closed-loop action executor. Backend (Python 3.12), Next.js PWA
  (PULSE/VIPs/Ops/Kitchen tabs), and 4 CloudFormation nested stacks.
- LUMI **shared-layer wiring** for PULSE (additive per the AGENTS.md cross-feature
  carve-out): `NEW_AND_OLD_IMAGES` DynamoDB Streams + stream-ARN outputs on the five
  operational tables; three read-only Gateway tools (`get_sister_property_availability`,
  `get_walkable_guests`, `get_room_move_candidates`); a scoped rooms-table `Scan` IAM grant.
- PULSE **Kitchen tab** served from a `pulse-kitchen` DynamoDB table via a read API,
  seeded by a CloudFormation `Custom::SeedData` custom resource.
- Root Makefile **`deploy-all`** orchestrator: deploys LUMI, captures its stack
  outputs (Cognito, Tool Lambda ARN, the five DataStack stream ARNs) plus the shared
  Gateway endpoint from SSM, and threads them into the PULSE deploy and Gateway
  tool registration in the correct order.
- `[ops-read]` optional-dependency group for the PULSE backend (`strands-agents`,
  `mcp-proxy-for-aws`) so the VIPs/Ops facade Lambda can reach the shared Gateway.
- **StayOS shell branding**: a platform logo mark (`logo.svg` + matching
  `favicon.svg`) — an "OS window" tile holding a rising spectrum arc in the
  StayOS accent gradient — surfaced via a reusable `StayOSLogo` lockup ("Stay" +
  gradient "OS") on both the login and launcher views.
- **First-login onboarding tour** on the shell launcher: a two-step coachmark that
  highlights the LUMI card (AI morning brief) then advances to PULSE (real-time
  alerts), click-to-advance with a Skip control. Shown once per GM per browser
  (`useOnboarding` persists a per-email flag in the shared `stayos.*` storage).
- **`shared/AGENTS.md`**: agent guide for the cross-feature layer documenting the
  `@stayos/auth` module, its build-time path-alias consumption, and the
  three-consumer change discipline.

### Changed
- StayOS shell header **centered** (logo + wordmark stacked, Logout floated
  top-right) and now shows the signed-in GM's **email** instead of the login alias.
- Lifted and brightened the focal dot on the StayOS logo mark so it reads as a
  distinct rising element above the arc.
- Marked **PULSE as deployed and running** in `us-east-1` across its docs
  (`pulse/README.md`, `pulse/AGENTS.md`) and closed the deploy task (Task 25) in
  the PULSE spec checklist — replacing the prior "built and tested; deploy is the
  one remaining manual step" status.

### Fixed
- PULSE deploy no longer fails to find the shared AgentCore Gateway: its SSM lookups
  now key off the LUMI namespace (`/lumi/gateway/*`), where LUMI actually writes the
  Gateway id/endpoint, instead of `/pulse/*`.
- `make package-backend` now bundles the MCP client stack, so the deployed
  `pulse-ops-read` facade no longer crashes at runtime with `ModuleNotFoundError`.

## [1.4.0] - 2026-08-17

Tagged `v1.4`. Repository restructured into a multi-feature monorepo and the LUMI
voice agent migrated to Amazon Bedrock AgentCore.

### Added
- Second feature **PULSE** introduced as planning-only (AI-PLC discovery docs, no
  code yet); added to the StayOS landing page, replacing the Ops Forecasting card.
- AgentCore **chat agent** with Gateway tool integration and markdown rendering.
- CodeBuild container build pipeline for AgentCore deployment.
- Suggested questions added to the LUMI voice overlay.

### Changed
- **Restructured the repo into a feature-based layout** — `lumi/` (built feature),
  `pulse/` (planned feature), and `shared/` (cross-feature layer). Each feature is
  now self-contained with its own backend, frontend, infrastructure, and docs.
- Renamed the top-level `platform/` directory to `shared/` for clarity.
- Migrated the LUMI voice agent from ECS Fargate to **Amazon Bedrock AgentCore**.
- Named the voice agent **LUMI**.
- Consolidated CloudFormation from 8 nested stacks down to 4.
- Derived `BRIEFS_TABLE_NAME` from `StackPrefix` instead of hardcoding `lumi-briefs`.

### Fixed
- Resolved Gateway integration bugs in the chat agent.
- Resolved critical AgentCore migration deploy blockers and High-severity code
  review findings.
- Deploy no longer fails when Gateway WAF association hits AWS-side propagation delay.
- Voice agent VIP-data consistency and end-to-end reliability on AgentCore.
- Removed `MinimumProtocolVersion` from the CloudFront default certificate.

### Removed
- Chat-agent spec directory and architecture-diagram generator scripts.
- Hardcoded account IDs, personal paths, and per-account deployment notes from tracked files.
- "Start here" section from `pulse/README.md`; dead links from `lumi/llms.txt`.

### Security
- Added `DeletionPolicy: Retain` to dataset tables and secrets.
- Removed hardcoded `AppPassword` defaults from CloudFormation templates.
- Replaced ASIA test key with the AWS docs example key (`AKIAIOSFODNN7EXAMPLE`).

## [Voice Overlay & Open-Source Readiness] - 2026-08-12

### Added
- LUMI voice overlay feature (`feat/lumi-voice-overlay`).

### Changed
- Upgraded the frontend to **Next.js 15, React 19, Vitest 4, TypeScript 5.8**.
- Refactored README for clarity and conciseness; optimized the voice agent.

### Fixed
- Updated vulnerable dependencies.
- Open-source readiness pass: Makefile, security, and scan findings.

### Removed
- `plan.html` planning document and the resolved `semantic-review` folder.

## [Voice Agent (Nova Sonic)] - 2026-08-10 to 2026-08-11

### Added
- **Voice agent** with Amazon Nova Sonic (STT/TTS over WebSocket) — push-to-talk
  conversational Q&A over the shared dataset (`feat/voice-agent-nova2-sonic`).
- Voice agent requirements specification.
- **AWS WAF** protection on CloudFront (US-only geographic restriction).
- StayOS landing page and refreshed branding.
- Data model reference and architecture documentation; multiple demo GIF refreshes.

### Changed
- Enabled Nova Sonic tools (`inputSchema.json` must be a JSON string).
- Reverted to a mobile-only layout; updated the KPI grid; added a demo disclaimer.
- Replaced the voice agent architecture diagram with an AWS-icon diagram.
- Updated the LUMI API specification with StayOS integration and WAF details.

### Fixed
- Resolved Nova Sonic bidirectional stream failures and timeouts.

## [Datasets, Ops & Accessibility] - 2026-08-06 to 2026-08-07

### Added
- **Hotel dataset generator** with multi-property seeding (~24k items across tables).
- VIP arrival curation and ranking with deduplication in the data puller.
- Rooms Out-of-Order (OOO) detail modal.
- Past-brief detail view and brief history.
- Voice assistant button with split bottom-navigation layout.
- Historical seed data and revenue trends.
- Keyboard navigation and focus states for past briefs (accessibility).
- Device detection and responsive UI layouts.

### Changed
- Enhanced the deployment pipeline with a Bedrock preflight check and improved Makefile.
- Updated Next.js to 14.2.35; added gitleaks ignore rules.

### Fixed
- Service-worker audio cache switched to network-first for daily brief updates.
- Force Lambda code updates on deploy.

## [0.1.0 - Initial LUMI Release] - 2026-08-05

Initial prototype: **LUMI**, the General Manager's daily intelligence brief.

### Added
- Initial commit — LUMI GM Daily Intelligence Brief application.
- Per-GM **EventBridge Scheduler** schedules, timezone-aware (REQ-SCHED-1..8).
- 5 pilot GM accounts across 4 regions (reduced from an initial 20).
- LUMI "Dawn Horizon" logo, favicon, and PWA icons.
- Architecture and 7-stage pipeline diagrams; business-context README.
- Kiro hook to sync API and project documentation.
- Configurable brief length wired into the generation prompt.

### Changed
- Consolidated the Data and Storage CloudFormation stacks.
- Moved settings into the header; relocated the demo GIF and architecture sections.

### Removed
- SNS topic from the architecture (not needed for the pilot).
- Hardcoded account IDs from README and templates.

[1.4.0]: https://github.com/hejani/StayOS/releases/tag/v1.4
