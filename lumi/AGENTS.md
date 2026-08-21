# LUMI — Agent Guide (StayOS Feature 1)

LUMI is the daily GM intelligence brief: at each GM's delivery time it pulls
operational data, generates an AI summary + 60-90s Polly audio brief, and
serves it as a Next.js PWA, plus voice (Nova Sonic) and chat (Claude Sonnet)
Q&A agents over the same dataset. **Built and deployed.**

The root [`../AGENTS.md`](../AGENTS.md) applies in full (safety rules,
PYQUALITY, NAMING, testing, runtime/stack). This file adds only LUMI specifics.
`StackPrefix = lumi`, region `us-east-1`.

LUMI is served at **`/lumi`** on the shared StayOS CloudFront distribution
(`basePath`/`assetPrefix` = `/lumi`). The StayOS shell owns the site root `/`
(unified login + feature launcher) and PULSE owns `/pulse`. LUMI does not host
its own login as the entry point: it consumes the shared `@stayos/auth` module
(from `shared/auth/`) via a build-time path alias, trusts the shared browser
session (single sign-on), and redirects unauthenticated users to the shell at
`/`. `src/lib/auth.ts` is a thin adapter over `@stayos/auth`; `/lumi/login` is a
deep-link fallback only.

## Structure

- `backend/functions/` — Lambdas: `api` (REST router + handlers), `orchestrator` (brief-generation pipeline: data_puller, brief_generator, audio_synthesizer, action_prioritizer), `seed-data` (CloudFormation custom resource seeding Cognito/DynamoDB/schedules), `tools` (`lumi-tools` Lambda: the 5 read-only hotel-ops tools behind the AgentCore Gateway).
- `backend/tools/tool-schema.json` — single source of truth for the shared Gateway tool definitions (name, description, inputSchema). Read at `gateway-deploy` time to register the Gateway target.
- `backend/services/` — containerized AgentCore Runtime agents: `voice-agent` (Nova Sonic, calls its 5 tools in-process for latency) and `chat-agent` (Strands + Claude Sonnet, discovers/calls the same tools via the Gateway over MCP).
- `backend/layers/dependencies/` — shared Lambda dependencies layer.
- `frontend/` — Next.js 15 App Router PWA (static export to `out/`), served under `/lumi` (`basePath: '/lumi'`). Raw asset/redirect/service-worker paths use the `withBase()` helper in `src/lib/constants.ts`; auth is the shared `@stayos/auth` module.
- `infrastructure/` — CloudFormation root stack + 5 nested stacks: `data`, `auth`, `compute`, `voice`, `chat`.

## Commands (from `lumi/`)

```bash
# Full deploy (single command) — APP_PASSWORD is required, sets all 5 demo GM logins
make deploy APP_PASSWORD=YourSecurePassword123!

# Step-by-step
make deploy-infra          # CloudFormation nested stacks (aws cloudformation deploy)
make package-backend       # zip Lambda code + layer, upload to the deploy S3 bucket
make update-lambda-code    # force Lambda code refresh (CFN uses a static S3 key)
make gateway-deploy        # create/update AgentCore Gateway + register lumi-tools target + WAF
make voice-deploy          # build (CodeBuild ARM64) + deploy voice agent to AgentCore Runtime
make chat-deploy           # build + deploy chat agent to AgentCore Runtime
make deploy-frontend       # S3 sync frontend/out -> s3://<bucket>/lumi/ + CloudFront invalidation of /lumi/*
make reseed                # refresh the 30-day mock dataset
make generate-briefs       # async-trigger the orchestrator to generate today's briefs

# Tests + lint (run before claiming done)
make test                  # backend pytest + frontend
make test-backend          # cd backend && python3 -m pytest tests/ -v
make test-frontend         # cd frontend && npm test
make lint                  # flake8 + mypy (backend), npm run lint (frontend)

# Teardown of out-of-band agent resources
make voice-destroy / make chat-destroy / make gateway-destroy
```

Container builds run remotely on **CodeBuild (ARM64 Graviton)** — no local
Docker required; use `finch` if you need a local container. `make deploy`
requires only AWS CLI v2.27+ (for `bedrock-agentcore-control`).

## Key invariants

- **Read-only data integration.** The 5 dataset tables are seeded once and are read-only at runtime (`Query`/`GetItem` only). Do not add runtime writes to operational tables from LUMI.
- **The Gateway tool schema is the single source of truth.** `backend/tools/tool-schema.json` + `backend/functions/tools/lambda_function.py` define the shared tools. PULSE also consumes this same shared Gateway — do NOT break the existing tool contracts. Adding a tool is **additive** and requires no chat-agent redeploy (the agent discovers tools from the Gateway at session start).
- **The Tool Lambda mirrors the voice agent's in-process tools.** Keep `tools/lambda_function.py` and the voice agent's `tool_handlers.py` semantically aligned (same DynamoDB access patterns).
- **AgentCore agents deploy out-of-band** via CodeBuild ARM64 → ECR → AgentCore Runtime. Runtime/gateway IDs are tracked in SSM (`/lumi/voice/runtime-id`, `/lumi/chat/runtime-id`, `/lumi/gateway/gateway-id`, `/lumi/gateway/endpoint-url`), not in CloudFormation (no CFN resource type yet).
- **Auth:** the REST API uses the Cognito User Pool JWT authorizer; SigV4 WebSocket via Cognito Identity Pool (shared by voice + chat). Client-side auth is the shared `@stayos/auth` module (`localStorage` `stayos.*` session on the shared origin) — do NOT reintroduce a LUMI-local auth implementation or a per-app `sessionStorage` session; that would break single sign-on with the shell and PULSE. Unauthenticated redirects go to the shell root `/` (raw, not `withBase`).
- **Served under `/lumi`.** Keep `basePath`/`assetPrefix` = `/lumi` and route every raw asset/redirect/service-worker/manifest path through `withBase()`. Redirects to the StayOS shell are the one exception: they are a raw `/` (the shell is outside LUMI's basePath).

See `README.md` and `llms.txt` for the full architecture and file index.
