# Makefile - PULSE (StayOS Feature #2) build, test, validate & deploy
#
# PULSE is built and tested; deployment is the one remaining manual step.
# This Makefile mirrors LUMI's conventions (variable style, gateway/CodeBuild
# patterns) and drives the real build/test/deploy commands documented in
# pulse/README.md.
#
# Container builds use AWS Finch (`finch`), never Docker. Agent containers
# build remotely on CodeBuild (ARM64); `finch` is the documented local
# equivalent.
#
# Prerequisites: AWS CLI v2 (>= 2.27 for bedrock-agentcore-control), Python
# 3.12, Node.js 18+, zip, cfn-lint, finch. See pulse/README.md#deploy for the
# out-of-band prerequisites (MCP dep bundling, LUMI Streams enablement, shared
# Gateway tool registration, Triage Agent container).
#
# Quick start:
#   make help          # list all targets
#   make test          # backend + frontend test suites
#   make lint          # backend + frontend linters
#   make validate      # cfn-lint the CloudFormation templates
#   make deploy USER_POOL_ID=... USER_POOL_ARN=... RESERVATIONS_STREAM_ARN=... (see below)

# ─── Config ───────────────────────────────────────────────────
STACK_PREFIX ?= pulse
REGION       ?= us-east-1
PROFILE      ?=

# Directory layout (override only if the tree changes).
BACKEND_DIR  ?= backend
FRONTEND_DIR ?= frontend
INFRA_DIR    ?= infrastructure
BUILD_DIR    ?= build

# Derived AWS invocation: add `--profile` only when PROFILE is set.
AWS_PROFILE_FLAG := $(if $(PROFILE),--profile $(PROFILE),)
AWS := aws $(AWS_PROFILE_FLAG) --region $(REGION)

# Account + stack identity.
ACCOUNT_ID ?= $(shell $(AWS) sts get-caller-identity --query Account --output text 2>/dev/null)
STACK_NAME := $(STACK_PREFIX)-$(REGION)

# S3 deploy bucket holding the shared Lambda package + packaged nested
# templates. Account-scoped for global uniqueness (S3 names are global) and to
# satisfy NAMING-02 (${StackPrefix}-<purpose>-<account-id>), mirroring LUMI's
# stayos-deploy-<account-id>. Threaded into the nested stacks via the root
# stack's DeployBucket parameter (see root-stack.yaml) so all references stay
# in sync; the nested-stack DeployBucket defaults are fallback only.
DEPLOY_BUCKET     ?= pulse-deploy-$(ACCOUNT_ID)
LAMBDA_CODE_S3_KEY ?= functions/pulse-backend.zip
LAMBDA_ZIP        := $(BUILD_DIR)/pulse-backend.zip
# The shared Lambda deployment zip is built on x86_64 Linux via CodeBuild (not
# locally) so native wheels (e.g. pydantic_core via the [ops-read] extra) match
# the Lambda runtime. Project + source key mirror the CFN PulseBackendBuildProject.
BACKEND_BUILD_PROJECT ?= $(STACK_PREFIX)-backend-build
BACKEND_SOURCE_KEY    ?= backend-source/backend-source.zip
PACKAGED_TEMPLATE := $(BUILD_DIR)/packaged-root-stack.yaml

# Triage Agent (AgentCore Runtime). Per the StayOS shared-resource principle,
# the triage container is built on LUMI's EXISTING shared CodeBuild project and
# pushed to LUMI's EXISTING shared ECR repo (no new CodeBuild project or ECR
# repo is created for PULSE). The shared chat-agent build project is a generic
# ARM64 container builder (same buildspec/role); triage-build reuses it via
# start-build source/env overrides. The triage image lives in the shared repo
# under a distinct 'triage-latest' tag so it does not collide with the chat
# agent's ':latest'. Override any of these only if the shared owner changes.
TRIAGE_MODEL_ID        ?= us.anthropic.claude-sonnet-4-6
# Shared LUMI build resources reused by PULSE (owned by LUMI's voice/chat stacks).
SHARED_BUILD_PROJECT   ?= $(LUMI_STACK_PREFIX)-chat-agent-build
SHARED_DEPLOY_BUCKET   ?= $(LUMI_STACK_PREFIX)-deploy-$(ACCOUNT_ID)
SHARED_AGENT_ECR_REPO  ?= $(LUMI_STACK_PREFIX)-chat-agent
TRIAGE_IMAGE_TAG       ?= triage-latest
# Upload under the chat-agent-source/ prefix: the shared build role's S3 read
# policy is scoped to that exact prefix, so reusing it needs no IAM change.
TRIAGE_SOURCE_KEY      ?= chat-agent-source/triage-agent-source.zip
# Deferred (=) so LUMI_STACK_PREFIX (defined below) is resolved at use-time,
# not at this line (avoids an empty prefix -> ".../-chat-agent" bad tag).
TRIAGE_ECR_URI          = $(ACCOUNT_ID).dkr.ecr.$(REGION).amazonaws.com/$(SHARED_AGENT_ECR_REPO)
TRIAGE_ROLE_NAME       := $(STACK_PREFIX)-triage-agentcore-role-$(REGION)
TRIAGE_RUNTIME_NAME    := $(STACK_PREFIX)_triage_agent
TRIAGE_RUNTIME_SSM     := /$(STACK_PREFIX)/triage/runtime-arn

# Shared StayOS AgentCore Gateway (owned by LUMI; PULSE adds tools to it).
# The Gateway id/endpoint live in SSM under the LUMI namespace (LUMI's
# gateway-deploy writes /lumi/gateway/*), NOT under PULSE's StackPrefix - so
# these paths key off LUMI_STACK_PREFIX, not STACK_PREFIX. Override
# LUMI_STACK_PREFIX only if the shared Gateway owner's prefix ever changes.
LUMI_STACK_PREFIX     ?= stayos
GATEWAY_ID_SSM        := /$(LUMI_STACK_PREFIX)/gateway/gateway-id
GATEWAY_ENDPOINT_SSM  := /$(LUMI_STACK_PREFIX)/gateway/endpoint-url
GATEWAY_TARGET_NAME   ?= tools
# PULSE tool schema + the shared Tool Lambda ARN the Gateway target invokes.
# These are deploy-time inputs (the shared Gateway is provisioned out-of-band
# by LUMI); see pulse/README.md#deploy prerequisite 3. Override on the CLI.
GATEWAY_TOOL_SCHEMA   ?= ../lumi/backend/tools/tool-schema.json
TOOL_LAMBDA_ARN       ?=

# ─── Deploy-time parameters (threaded to the root stack) ──────
# Values only known at deploy time; pass on the CLI or export. Empty defaults
# let CloudFormation apply template defaults where they exist. The five stream
# ARNs and the Cognito user pool ARN/ID have NO template default and are
# required by `make deploy` (guarded below). See pulse/README.md#deploy.
USER_POOL_ID            ?=
USER_POOL_ARN           ?=
USER_POOL_CLIENT_ID     ?=
WAF_WEB_ACL_ARN         ?=
VAPID_PUBLIC_KEY        ?=
RESERVATIONS_STREAM_ARN ?=
ROOMS_STREAM_ARN        ?=
GUESTS_STREAM_ARN       ?=
REVENUES_STREAM_ARN     ?=
WORK_ORDERS_STREAM_ARN  ?=
# Operational-table ARNs (IAM scoping for the rule-engine OperationalRead and
# the API OperationalWriteBack policies) and names (runtime env for the Action
# Executor / Simulator). Same five LUMI tables as the stream ARNs above; the
# root Makefile deploy-all derives these from the stream ARNs and threads them.
# Required by `make deploy` (guarded) so the IAM policies never get an empty
# Resource (see BUG-006).
RESERVATIONS_TABLE_ARN  ?=
ROOMS_TABLE_ARN         ?=
GUESTS_TABLE_ARN        ?=
REVENUES_TABLE_ARN      ?=
WORK_ORDERS_TABLE_ARN   ?=
RESERVATIONS_TABLE_NAME ?=
ROOMS_TABLE_NAME        ?=
GUESTS_TABLE_NAME       ?=
GATEWAY_ENDPOINT_URL    ?=
TRIAGE_RUNTIME_ARN      ?=
ENABLE_DEMO_SIMULATOR   ?= true

# ─── Shared frontend hosting (Option A: /pulse path on LUMI CloudFront) ───────
# PULSE's static export is served from the /pulse/ prefix of the SHARED StayOS
# (LUMI) S3 bucket + CloudFront distribution - one origin, one Cognito session,
# one WAF. deploy-frontend syncs out/ into s3://<lumi-frontend>/pulse/ and
# invalidates /pulse/*. These resolve LUMI's resources (a cross-feature READ; no
# LUMI files are modified). Override if LUMI's prefix/stack name differs.
LUMI_STACK          := $(LUMI_STACK_PREFIX)-$(REGION)
LUMI_FRONTEND_BUCKET ?= $(LUMI_STACK_PREFIX)-frontend-$(ACCOUNT_ID)
# NEXT_PUBLIC_* build-time inputs for the PULSE PWA (mirrors LUMI's env). The API
# URL is the PULSE stack's ApiEndpoint output when unset; Cognito comes from the
# shared LUMI user pool.
PULSE_API_URL       ?=
COGNITO_CLIENT_ID   ?= $(USER_POOL_CLIENT_ID)
COGNITO_REGION      ?= $(REGION)

.PHONY: help test test-backend test-frontend lint lint-backend lint-frontend \
        build-frontend write-frontend-env deploy-frontend validate ensure-bucket \
        package package-backend package-infra ensure-code-placeholder \
        update-lambda-code deploy _require-deploy-vars \
        gateway-deploy triage-build triage-deploy clean kitchen-reseed seed-run

.DEFAULT_GOAL := help

# ─── Help ─────────────────────────────────────────────────────
help: ## List available targets
	@echo "PULSE (StayOS Feature #2) - make targets:"
	@echo ""
	@grep -hE '^[a-zA-Z0-9_-]+:.*?## ' $(MAKEFILE_LIST) \
		| sort \
		| awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'
	@echo ""
	@echo "Config: STACK_PREFIX=$(STACK_PREFIX) REGION=$(REGION) DEPLOY_BUCKET=$(DEPLOY_BUCKET)"
	@echo "        PROFILE=$(if $(PROFILE),$(PROFILE),<default>)  STACK_NAME=$(STACK_NAME)"

# ─── Test ─────────────────────────────────────────────────────
test: test-backend test-frontend ## Run backend + frontend test suites
	@echo "All PULSE tests passed"

test-backend: ## Run backend pytest (unit + Hypothesis property tests)
	@echo "Running backend tests..."
	@cd $(BACKEND_DIR) && python3 -m pytest

test-frontend: ## Run frontend vitest (unit + fast-check) once
	@echo "Running frontend tests..."
	@cd $(FRONTEND_DIR) && npx vitest run

# ─── Lint ─────────────────────────────────────────────────────
lint: lint-backend lint-frontend ## Lint backend + frontend
	@echo "Lint clean"

lint-backend: ## Lint backend with ruff (PEP 8, isort, pydocstyle)
	@echo "Linting backend..."
	@cd $(BACKEND_DIR) && ruff check src tests

lint-frontend: ## Lint frontend with next lint / eslint
	@echo "Linting frontend..."
	@cd $(FRONTEND_DIR) && npm run lint

# ─── Frontend build ───────────────────────────────────────────
build-frontend: ## Build the Next.js PWA (static export to out/)
	@echo "Building frontend..."
	@# Install deps first (B1): on a clean machine node_modules does not exist, so
	@# `next build` would fail. Mirror LUMI/shell (npm ci --legacy-peer-deps) but
	@# keep build output visible for diagnosability (no 2>/dev/null): redirect to a
	@# log and tail it only if the build fails.
	@cd $(FRONTEND_DIR) && npm ci --legacy-peer-deps --silent && \
		( npm run build > build-frontend.log 2>&1 || \
		  { echo "PULSE frontend build FAILED - last 40 lines:"; tail -n 40 build-frontend.log; exit 1; } )

# Generate frontend/.env.production from stack outputs + shared Cognito, mirroring
# LUMI's write-frontend-env. API URL defaults to the PULSE stack's ApiEndpoint.
write-frontend-env: ## Write frontend/.env.production from stack outputs + Cognito
	@echo "Generating PULSE frontend env..."
	@API_URL="$(PULSE_API_URL)"; \
	if [ -z "$$API_URL" ]; then \
		API_URL=$$($(AWS) cloudformation describe-stacks --stack-name $(STACK_NAME) \
			--query "Stacks[0].Outputs[?OutputKey=='ApiEndpoint'].OutputValue" \
			--output text 2>/dev/null); \
	fi; \
	printf '%s\n' \
		"# Auto-generated by make write-frontend-env - do not edit manually" \
		"NEXT_PUBLIC_API_URL=$$API_URL" \
		"NEXT_PUBLIC_COGNITO_CLIENT_ID=$(COGNITO_CLIENT_ID)" \
		"NEXT_PUBLIC_COGNITO_REGION=$(COGNITO_REGION)" \
		"NEXT_PUBLIC_AWS_REGION=$(REGION)" \
		> $(FRONTEND_DIR)/.env.production
	@echo "Wrote $(FRONTEND_DIR)/.env.production"

# Deploy the PULSE static export to the /pulse/ prefix of the SHARED LUMI
# frontend bucket, then invalidate /pulse/* on the shared distribution. LUMI's
# CloudFront (single S3 origin + url-rewrite function + OAC + WAF) already serves
# this prefix - no LUMI infra change. next.config.js basePath=/pulse makes every
# route/asset resolve under /pulse. Requires LUMI to be deployed (shared bucket +
# distribution must exist).
deploy-frontend: write-frontend-env build-frontend ## Publish PULSE PWA to /pulse on the shared LUMI CloudFront
	@echo "Deploying PULSE frontend to s3://$(LUMI_FRONTEND_BUCKET)/pulse/ ..."
	@if ! $(AWS) s3api head-bucket --bucket $(LUMI_FRONTEND_BUCKET) 2>/dev/null; then \
		echo "ERROR: shared LUMI frontend bucket $(LUMI_FRONTEND_BUCKET) not found."; \
		echo "Deploy LUMI first (make -C ../lumi deploy) or set LUMI_FRONTEND_BUCKET."; \
		exit 1; \
	fi
	@$(AWS) s3 sync $(FRONTEND_DIR)/out/ s3://$(LUMI_FRONTEND_BUCKET)/pulse/ --delete --quiet
	@echo "Invalidating /pulse/* on the shared LUMI distribution..."
	@DIST_ID=$$($(AWS) cloudformation describe-stacks --stack-name $(LUMI_STACK) \
		--query "Stacks[0].Outputs[?OutputKey=='FrontendDistributionId'].OutputValue" \
		--output text 2>/dev/null) && \
	if [ -n "$$DIST_ID" ] && [ "$$DIST_ID" != "None" ]; then \
		$(AWS) cloudfront create-invalidation --distribution-id "$$DIST_ID" \
			--paths "/pulse/*" > /dev/null && \
		echo "Invalidated /pulse/* on $$DIST_ID"; \
	else \
		echo "WARNING: could not resolve LUMI FrontendDistributionId; skipped invalidation."; \
	fi
	@echo "PULSE frontend live at <lumi-cloudfront-domain>/pulse/"

# ─── IaC validation ───────────────────────────────────────────
validate: ## cfn-lint the root + nested CloudFormation templates
	@echo "Validating CloudFormation templates..."
	@cd $(INFRA_DIR) && cfn-lint root-stack.yaml nested-stacks/*.yaml
	@echo "Templates valid"

# ─── Packaging ────────────────────────────────────────────────
# Ensure the S3 deploy bucket exists (created once; safe to re-run).
ensure-bucket: ## Create the S3 deploy bucket if it does not exist
	@$(AWS) s3api head-bucket --bucket $(DEPLOY_BUCKET) 2>/dev/null \
		|| $(AWS) s3 mb s3://$(DEPLOY_BUCKET) > /dev/null
	@echo "Deploy bucket ready: s3://$(DEPLOY_BUCKET)"

# Build the single shared Lambda deployment package (pulse-backend.zip) from
# the backend src layout + runtime deps, and upload it to the key the nested
# stacks reference (functions/pulse-backend.zip). The `[ops-read]` extra pulls
# in the MCP client stack (mcp-proxy-for-aws, strands-agents) required by the
# pulse-ops-read (VIPs/Ops) facade to reach the shared StayOS Gateway; the
# other PULSE Lambdas ignore it (lazy-imported only inside the facade).
package-backend: ensure-bucket ## Build the shared Lambda zip on CodeBuild (x86_64 Linux) + upload
	@echo "Packaging backend Lambda deployment zip (via CodeBuild, x86_64 Linux)..."
	@# Build the zip on CodeBuild rather than locally so native wheels (e.g.
	@# pydantic_core, pulled by the [ops-read] MCP/strands extra) match the Lambda
	@# runtime (x86_64 / python3.12). Building on a non-Linux host packages host
	@# wheels that fail at runtime with
	@# "No module named 'pydantic_core._pydantic_core'" (BUG-017). No Docker/Finch.
	@echo "  [backend] Staging backend source (pyproject + src + README)..."
	@rm -rf $(BUILD_DIR)/backend-src
	@mkdir -p $(BUILD_DIR)/backend-src
	@cp -R $(BACKEND_DIR)/pyproject.toml $(BACKEND_DIR)/src $(BUILD_DIR)/backend-src/
	@cp $(BACKEND_DIR)/README.md $(BUILD_DIR)/backend-src/ 2>/dev/null || true
	@cd $(BUILD_DIR)/backend-src && zip -r ../backend-source.zip . \
		-x "*.pyc" "__pycache__/*" "*.egg-info/*" > /dev/null
	@echo "  [backend] Uploading source to s3://$(DEPLOY_BUCKET)/$(BACKEND_SOURCE_KEY)..."
	@$(AWS) s3 cp $(BUILD_DIR)/backend-source.zip s3://$(DEPLOY_BUCKET)/$(BACKEND_SOURCE_KEY) --quiet
	@echo "  [backend] Starting CodeBuild project $(BACKEND_BUILD_PROJECT)..."
	@BUILD_ID=$$($(AWS) codebuild start-build --project-name $(BACKEND_BUILD_PROJECT) \
		--query 'build.id' --output text) && \
	echo "  [backend] Build started: $$BUILD_ID" && \
	while true; do \
		STATUS=$$($(AWS) codebuild batch-get-builds --ids $$BUILD_ID \
			--query 'builds[0].buildStatus' --output text); \
		if [ "$$STATUS" = "SUCCEEDED" ]; then \
			echo "  [backend] Build succeeded: s3://$(DEPLOY_BUCKET)/$(LAMBDA_CODE_S3_KEY)"; break; \
		elif [ "$$STATUS" = "IN_PROGRESS" ]; then sleep 10; \
		else \
			LOG_URL=$$($(AWS) codebuild batch-get-builds --ids $$BUILD_ID \
				--query 'builds[0].logs.deepLink' --output text); \
			echo "  [backend] CodeBuild failed ($$STATUS). Logs: $$LOG_URL"; exit 1; \
		fi; \
	done

# Force a Lambda code refresh on all PULSE functions from the freshly-built
# shared zip. CloudFormation references a STATIC S3 key (functions/pulse-backend.zip),
# so it cannot detect when the zip content changes; this updates every function
# after a build so the latest code is always running (mirrors LUMI's
# update-lambda-code). Safe to run repeatedly; tolerant of a not-yet-created fn.
update-lambda-code: ## Refresh all PULSE Lambda code from the shared zip
	@echo "Refreshing PULSE Lambda function code from s3://$(DEPLOY_BUCKET)/$(LAMBDA_CODE_S3_KEY)..."
	@for FN in pulse-api pulse-rule-evaluator pulse-triage-invoker \
	           pulse-alert-timeout-sweeper \
	           pulse-escalation-service \
	           pulse-action-executor pulse-history-writer pulse-info-batcher \
	           pulse-push-service pulse-ops-read pulse-demo-simulator \
	           pulse-kitchen-seed pulse-rules-seed; do \
		$(AWS) lambda update-function-code \
			--function-name "$$FN" \
			--s3-bucket $(DEPLOY_BUCKET) \
			--s3-key $(LAMBDA_CODE_S3_KEY) > /dev/null 2>&1 \
			&& echo "  updated $$FN" \
			|| echo "  skipped $$FN (not found or update failed)"; \
	done
	@echo "Lambda code refresh requested."

# `aws cloudformation package` uploads the nested templates to S3 and rewrites
# the root template's TemplateURLs, producing build/packaged-root-stack.yaml.
package-infra: ensure-bucket ## Package nested templates for deploy
	@echo "Packaging CloudFormation nested templates..."
	@mkdir -p $(BUILD_DIR)
	@$(AWS) cloudformation package \
		--template-file $(INFRA_DIR)/root-stack.yaml \
		--s3-bucket $(DEPLOY_BUCKET) \
		--s3-prefix cfn-templates \
		--output-template-file $(PACKAGED_TEMPLATE) > /dev/null
	@echo "Wrote $(PACKAGED_TEMPLATE)"

# Full packaging: nested templates + ensure a Lambda-code object exists so the
# stack can reference it. The REAL backend zip is built on CodeBuild AFTER the
# stack exists (deploy -> package-backend -> update-lambda-code), because the
# CodeBuild project that builds it is itself created by the stack (bootstrap).
package: ensure-code-placeholder package-infra ## Package templates (+ ensure Lambda-code object)
	@echo "Packaging complete"

# Ensure a Lambda-code object exists at the deploy key so `cloudformation deploy`
# can validate/create the Lambdas on a first deploy (CFN requires the S3 object
# to exist). If a real build already produced one, leave it; otherwise upload a
# tiny placeholder. package-backend later overwrites it with the real CodeBuild
# output and update-lambda-code refreshes the functions.
ensure-code-placeholder: ensure-bucket
	@if $(AWS) s3api head-object --bucket $(DEPLOY_BUCKET) --key $(LAMBDA_CODE_S3_KEY) >/dev/null 2>&1; then \
		echo "Lambda-code object present: s3://$(DEPLOY_BUCKET)/$(LAMBDA_CODE_S3_KEY)"; \
	else \
		echo "Uploading placeholder Lambda-code object (first deploy)..."; \
		mkdir -p $(BUILD_DIR)/placeholder/pulse/seed && \
		: > $(BUILD_DIR)/placeholder/pulse/__init__.py && \
		: > $(BUILD_DIR)/placeholder/pulse/seed/__init__.py && \
		printf '%s\n' \
			'"""First-deploy placeholder for the shared PULSE Lambda package."""' \
			'import json, urllib.request' \
			'' \
			'' \
			'def _cfn_ok(event, context):' \
			'    """Respond SUCCESS to a CloudFormation custom resource (no-op).' \
			'' \
			'    The real code is built on CodeBuild AFTER the stack exists, then a' \
			'    second deploy with bumped seed Triggers runs the real seeds. This' \
			'    placeholder must NOT raise at import or invoke, or the seed custom' \
			'    resources would hang the first stack create (BUG: No module pulse).' \
			'    """' \
			'    if "ResponseURL" not in event:' \
			'        return' \
			'    body = json.dumps({' \
			'        "Status": "SUCCESS",' \
			'        "PhysicalResourceId": event.get("PhysicalResourceId")' \
			'            or (context.log_stream_name if context else "placeholder"),' \
			'        "StackId": event.get("StackId"),' \
			'        "RequestId": event.get("RequestId"),' \
			'        "LogicalResourceId": event.get("LogicalResourceId"),' \
			'        "Data": {"placeholder": True},' \
			'    }).encode("utf-8")' \
			'    req = urllib.request.Request(' \
			'        url=event["ResponseURL"], data=body, method="PUT",' \
			'        headers={"content-type": "", "content-length": str(len(body))})' \
			'    urllib.request.urlopen(req)  # noqa: S310 (fixed CFN URL)' \
			'' \
			'' \
			'def lambda_handler(event, context):' \
			'    """Placeholder handler: succeed as a CFN no-op; error on direct invoke."""' \
			'    if isinstance(event, dict) and "RequestType" in event:' \
			'        _cfn_ok(event, context)' \
			'        return' \
			'    raise RuntimeError("placeholder - run package-backend to build real code")' \
			> $(BUILD_DIR)/placeholder/pulse/seed/kitchen_seed.py && \
		cp $(BUILD_DIR)/placeholder/pulse/seed/kitchen_seed.py \
			$(BUILD_DIR)/placeholder/pulse/seed/rules_seed.py && \
		printf 'def lambda_handler(event, context):\n    raise RuntimeError("placeholder - run package-backend")\n' \
			> $(BUILD_DIR)/placeholder/lambda_function.py && \
		(cd $(BUILD_DIR)/placeholder && zip -q -r ../placeholder.zip lambda_function.py pulse) && \
		$(AWS) s3 cp $(BUILD_DIR)/placeholder.zip s3://$(DEPLOY_BUCKET)/$(LAMBDA_CODE_S3_KEY) --quiet; \
	fi

# ─── Deploy (manual step) ─────────────────────────────────────
# Guard the parameters that have no template default. `make deploy` fails fast
# with a clear message if any are missing (see pulse/README.md#deploy).
_require-deploy-vars:
	@missing=""; \
	for pair in \
		"USER_POOL_ID=$(USER_POOL_ID)" \
		"USER_POOL_ARN=$(USER_POOL_ARN)" \
		"RESERVATIONS_STREAM_ARN=$(RESERVATIONS_STREAM_ARN)" \
		"ROOMS_STREAM_ARN=$(ROOMS_STREAM_ARN)" \
		"GUESTS_STREAM_ARN=$(GUESTS_STREAM_ARN)" \
		"REVENUES_STREAM_ARN=$(REVENUES_STREAM_ARN)" \
		"WORK_ORDERS_STREAM_ARN=$(WORK_ORDERS_STREAM_ARN)" \
		"RESERVATIONS_TABLE_ARN=$(RESERVATIONS_TABLE_ARN)" \
		"ROOMS_TABLE_ARN=$(ROOMS_TABLE_ARN)" \
		"GUESTS_TABLE_ARN=$(GUESTS_TABLE_ARN)" \
		"REVENUES_TABLE_ARN=$(REVENUES_TABLE_ARN)" \
		"WORK_ORDERS_TABLE_ARN=$(WORK_ORDERS_TABLE_ARN)"; do \
		val="$${pair#*=}"; \
		if [ -z "$$val" ]; then missing="$$missing $${pair%%=*}"; fi; \
	done; \
	if [ -n "$$missing" ]; then \
		echo ""; \
		echo "ERROR: missing required deploy parameters:$$missing"; \
		echo ""; \
		echo "These come from the LUMI platform (Cognito user pool + the five"; \
		echo "operational-table DynamoDB Stream ARNs). See pulse/README.md#deploy."; \
		echo ""; \
		echo "Example:"; \
		echo "  make deploy \\"; \
		echo "    USER_POOL_ID=us-east-1_xxxx USER_POOL_ARN=arn:aws:cognito-idp:... \\"; \
		echo "    RESERVATIONS_STREAM_ARN=arn:... ROOMS_STREAM_ARN=arn:... \\"; \
		echo "    GUESTS_STREAM_ARN=arn:... REVENUES_STREAM_ARN=arn:... \\"; \
		echo "    WORK_ORDERS_STREAM_ARN=arn:..."; \
		echo ""; \
		exit 1; \
	fi

# Deploy the packaged root stack. CloudFormation provisions the nested stacks
# in dependency order: pulse-data -> pulse-pipeline -> pulse-api ->
# pulse-observability (root-stack.yaml wires the DependsOn/GetAtt graph). This
# is the manual step - it is never auto-run.
deploy: _require-deploy-vars package ## Deploy PULSE (root -> data -> pipeline -> api -> observability)
	@echo "Deploying $(STACK_NAME) (this may take several minutes)..."
	@$(AWS) cloudformation deploy \
		--stack-name $(STACK_NAME) \
		--template-file $(PACKAGED_TEMPLATE) \
		--parameter-overrides \
			StackPrefix=$(STACK_PREFIX) \
			DeployBucket=$(DEPLOY_BUCKET) \
			TriageModelId=$(TRIAGE_MODEL_ID) \
			TriageRuntimeArn=$(TRIAGE_RUNTIME_ARN) \
			GatewayEndpointUrl=$(GATEWAY_ENDPOINT_URL) \
			EnableDemoSimulator=$(ENABLE_DEMO_SIMULATOR) \
			UserPoolId=$(USER_POOL_ID) \
			UserPoolArn=$(USER_POOL_ARN) \
			UserPoolClientId=$(USER_POOL_CLIENT_ID) \
			VapidPublicKey=$(VAPID_PUBLIC_KEY) \
			WafWebAclArn=$(WAF_WEB_ACL_ARN) \
			ReservationsStreamArn=$(RESERVATIONS_STREAM_ARN) \
			RoomsStreamArn=$(ROOMS_STREAM_ARN) \
			GuestsStreamArn=$(GUESTS_STREAM_ARN) \
			RevenuesStreamArn=$(REVENUES_STREAM_ARN) \
			ReservationsTableArn=$(RESERVATIONS_TABLE_ARN) \
			RoomsTableArn=$(ROOMS_TABLE_ARN) \
			GuestsTableArn=$(GUESTS_TABLE_ARN) \
			RevenuesTableArn=$(REVENUES_TABLE_ARN) \
			WorkOrdersTableArn=$(WORK_ORDERS_TABLE_ARN) \
			ReservationsTableName=$(RESERVATIONS_TABLE_NAME) \
			RoomsTableName=$(ROOMS_TABLE_NAME) \
			GuestsTableName=$(GUESTS_TABLE_NAME) \
			WorkOrdersStreamArn=$(WORK_ORDERS_STREAM_ARN) \
		--capabilities CAPABILITY_NAMED_IAM CAPABILITY_AUTO_EXPAND \
		--no-fail-on-empty-changeset
	@echo ""
	@echo "Building the shared Lambda zip on CodeBuild and refreshing function code..."
	@$(MAKE) package-backend STACK_PREFIX=$(STACK_PREFIX) REGION=$(REGION) PROFILE=$(PROFILE)
	@$(MAKE) update-lambda-code STACK_PREFIX=$(STACK_PREFIX) REGION=$(REGION) PROFILE=$(PROFILE)
	@echo ""
	@echo "Running PULSE data seeds against the freshly-deployed real code..."
	@# On first deploy the seed custom resources ran against the placeholder
	@# (a CFN no-op), so the tables are not yet seeded. Now that update-lambda-code
	@# has pushed the REAL pulse package, invoke the seed Lambdas directly (they
	@# support a no-ResponseURL direct invoke and are idempotent) so kitchen +
	@# rules data actually lands. This avoids a second cloudformation deploy and
	@# needs no template change.
	@$(MAKE) seed-run STACK_PREFIX=$(STACK_PREFIX) REGION=$(REGION) PROFILE=$(PROFILE)
	@echo ""
	@echo "PULSE deploy complete: $(STACK_NAME)"
	@echo "  API:      $$($(AWS) cloudformation describe-stacks --stack-name $(STACK_NAME) \
		--query \"Stacks[0].Outputs[?OutputKey=='ApiEndpoint'].OutputValue\" --output text 2>/dev/null)"
	@echo "  Realtime: $$($(AWS) cloudformation describe-stacks --stack-name $(STACK_NAME) \
		--query \"Stacks[0].Outputs[?OutputKey=='RealtimeHttpEndpoint'].OutputValue\" --output text 2>/dev/null)"
	@echo ""
	@echo "Next: register PULSE Gateway tools (make gateway-deploy) and deploy the"
	@echo "Triage Agent (make triage-deploy). See pulse/README.md#deploy."

# ─── Shared Gateway tool registration (out-of-band) ───────────
# Registers/updates the PULSE tools on the SHARED StayOS AgentCore Gateway
# target (the same Gateway LUMI's chat agent uses). AgentCore Gateway has no
# CloudFormation resource type, so this runs out-of-band from the nested
# stacks via the AWS CLI (mirrors LUMI's gateway-deploy). PULSE tool additions
# are additive to the shared target.
#
# Required (deploy-time inputs, see pulse/README.md#deploy prerequisite 3):
#   TOOL_LAMBDA_ARN     - ARN of the shared Tool Lambda the target invokes
#   GATEWAY_TOOL_SCHEMA - path to the tool schema JSON (inline payload)
# The shared Gateway id is read from SSM ($(GATEWAY_ID_SSM)).
gateway-deploy: ## Register PULSE tools on the shared StayOS Gateway target
	@if [ -z "$(TOOL_LAMBDA_ARN)" ]; then \
		echo "ERROR: TOOL_LAMBDA_ARN is required (shared Tool Lambda ARN)."; \
		echo "See pulse/README.md#deploy prerequisite 3."; \
		exit 1; \
	fi
	@echo "  [gateway] Reading shared Gateway id from SSM $(GATEWAY_ID_SSM)..."
	@GATEWAY_ID=$$($(AWS) ssm get-parameter --name "$(GATEWAY_ID_SSM)" \
		--query "Parameter.Value" --output text 2>/dev/null) && \
	if [ -z "$$GATEWAY_ID" ] || [ "$$GATEWAY_ID" = "None" ]; then \
		echo "  ERROR: no shared Gateway id in SSM $(GATEWAY_ID_SSM)."; \
		echo "  Deploy the shared StayOS Gateway (LUMI gateway-deploy) first."; \
		exit 1; \
	fi && \
	echo "  [gateway] Building target config from $(GATEWAY_TOOL_SCHEMA)..." && \
	TARGET_CONFIG=$$(python3 -c "import json, sys; tools = json.load(open(sys.argv[1]))['tools']; print(json.dumps({'mcp': {'lambda': {'lambdaArn': sys.argv[2], 'toolSchema': {'inlinePayload': tools}}}}))" "$(GATEWAY_TOOL_SCHEMA)" "$(TOOL_LAMBDA_ARN)") && \
	TARGET_ID=$$($(AWS) bedrock-agentcore-control list-gateway-targets \
		--gateway-identifier "$$GATEWAY_ID" \
		--query "items[?name=='$(GATEWAY_TARGET_NAME)'].targetId | [0]" --output text) && \
	if [ "$$TARGET_ID" != "None" ] && [ -n "$$TARGET_ID" ]; then \
		echo "  [gateway] Updating shared target $$TARGET_ID with PULSE tools..." && \
		$(AWS) bedrock-agentcore-control update-gateway-target \
			--gateway-identifier "$$GATEWAY_ID" \
			--target-id "$$TARGET_ID" \
			--name "$(GATEWAY_TARGET_NAME)" \
			--target-configuration "$$TARGET_CONFIG" \
			--credential-provider-configurations '[{"credentialProviderType":"GATEWAY_IAM_ROLE"}]' > /dev/null && \
		echo "  [gateway] Shared target updated"; \
	else \
		echo "  ERROR: shared target '$(GATEWAY_TARGET_NAME)' not found on Gateway $$GATEWAY_ID."; \
		echo "  The shared target is created by LUMI's gateway-deploy."; \
		exit 1; \
	fi

# ─── Triage Agent container build (CodeBuild, ARM64) ──────────
# Stages backend/src/pulse into the build context, zips the triage-agent
# source, uploads to S3, and triggers the CodeBuild project that builds the
# ARM64 image and pushes it to ECR. Local equivalent uses AWS Finch:
#   finch build --platform linux/arm64 -t $(STACK_PREFIX)-triage-agent \
#     -f Containerfile .
triage-build: ## Build the Triage Agent ARM64 container via the SHARED CodeBuild project
	@echo "  [triage] Staging build context (triage-agent + pulse package)..."
	@rm -rf $(BUILD_DIR)/triage-context
	@mkdir -p $(BUILD_DIR)/triage-context
	@cp -R $(BACKEND_DIR)/services/triage-agent/. $(BUILD_DIR)/triage-context/
	@cp -R $(BACKEND_DIR)/src/pulse $(BUILD_DIR)/triage-context/pulse
	@echo "  [triage] Zipping source..."
	@cd $(BUILD_DIR)/triage-context && zip -r ../triage-agent-source.zip . \
		-x "tests/*" "__pycache__/*" "*.pyc" "agentcore.yaml" ".pytest_cache/*" > /dev/null
	@echo "  [triage] Uploading source to the SHARED deploy bucket ($(SHARED_DEPLOY_BUCKET))..."
	@$(AWS) s3 cp $(BUILD_DIR)/triage-agent-source.zip \
		s3://$(SHARED_DEPLOY_BUCKET)/$(TRIAGE_SOURCE_KEY) --quiet
	@echo "  [triage] Starting SHARED CodeBuild project $(SHARED_BUILD_PROJECT) (source+env+buildspec overrides)..."
	@echo "  [triage] Reusing ECR repo $(SHARED_AGENT_ECR_REPO); pushing tag '$(TRIAGE_IMAGE_TAG)' (no new resources)..."
	@BUILDSPEC=$$(printf '%b' 'version: 0.2\nphases:\n  pre_build:\n    commands:\n      - aws ecr get-login-password --region $$AWS_DEFAULT_REGION | docker login --username AWS --password-stdin $$AWS_ACCOUNT_ID.dkr.ecr.$$AWS_DEFAULT_REGION.amazonaws.com\n  build:\n    commands:\n      - docker build --platform linux/arm64 -t $$ECR_REPO_URI:$$IMAGE_TAG -f Containerfile .\n  post_build:\n    commands:\n      - docker push $$ECR_REPO_URI:$$IMAGE_TAG\n      - echo "Pushed $$ECR_REPO_URI:$$IMAGE_TAG"\n'); \
	BUILD_ID=$$($(AWS) codebuild start-build --project-name $(SHARED_BUILD_PROJECT) \
		--source-location-override "$(SHARED_DEPLOY_BUCKET)/$(TRIAGE_SOURCE_KEY)" \
		--buildspec-override "$$BUILDSPEC" \
		--environment-variables-override \
			"name=ECR_REPO_URI,value=$(TRIAGE_ECR_URI),type=PLAINTEXT" \
			"name=IMAGE_TAG,value=$(TRIAGE_IMAGE_TAG),type=PLAINTEXT" \
			"name=AWS_ACCOUNT_ID,value=$(ACCOUNT_ID),type=PLAINTEXT" \
		--query 'build.id' --output text) && \
	echo "  [triage] Build started: $$BUILD_ID" && \
	while true; do \
		STATUS=$$($(AWS) codebuild batch-get-builds --ids $$BUILD_ID \
			--query 'builds[0].buildStatus' --output text); \
		if [ "$$STATUS" = "SUCCEEDED" ]; then \
			echo "  [triage] Build succeeded: $(TRIAGE_ECR_URI):$(TRIAGE_IMAGE_TAG)"; break; \
		elif [ "$$STATUS" = "IN_PROGRESS" ]; then sleep 10; \
		else \
			LOG_URL=$$($(AWS) codebuild batch-get-builds --ids $$BUILD_ID \
				--query 'builds[0].logs.deepLink' --output text); \
			echo "  CodeBuild failed ($$STATUS). Logs: $$LOG_URL"; exit 1; \
		fi; \
	done

# Create or update the Triage Agent AgentCore Runtime and write its ARN to SSM
# $(TRIAGE_RUNTIME_SSM) (consumed by the Rule Engine to InvokeAgentRuntime).
# Env vars are sourced from SSM + stack outputs (never hardcoded). The IAM role
# name is deterministic (${StackPrefix}-triage-agentcore-role-${Region}).
triage-deploy: triage-build ## Build + deploy the Triage Agent to AgentCore Runtime
	@echo "  [triage] Resolving runtime configuration..."
	@ROLE_ARN=$$($(AWS) iam get-role --role-name $(TRIAGE_ROLE_NAME) \
		--query 'Role.Arn' --output text) && \
	GATEWAY_ENDPOINT_URL=$$($(AWS) ssm get-parameter --name "$(GATEWAY_ENDPOINT_SSM)" \
		--query "Parameter.Value" --output text 2>/dev/null) && \
	ALERTS_TABLE_NAME=$$($(AWS) ssm get-parameter \
		--name "/$(STACK_PREFIX)/triage/alerts-table-name" \
		--query "Parameter.Value" --output text 2>/dev/null) && \
	REALTIME_HTTP_ENDPOINT=$$($(AWS) cloudformation describe-stacks \
		--stack-name $(STACK_NAME) \
		--query "Stacks[0].Outputs[?OutputKey=='RealtimeHttpEndpoint'].OutputValue" \
		--output text 2>/dev/null) && \
	ENV_VARS="{\"GATEWAY_ENDPOINT_URL\":\"$$GATEWAY_ENDPOINT_URL\",\"TRIAGE_MODEL_ID\":\"$(TRIAGE_MODEL_ID)\",\"ALERTS_TABLE_NAME\":\"$$ALERTS_TABLE_NAME\",\"REALTIME_HTTP_ENDPOINT\":\"$$REALTIME_HTTP_ENDPOINT\",\"AWS_DEFAULT_REGION\":\"$(REGION)\",\"LOG_LEVEL\":\"INFO\"}" && \
	if RUNTIME_ID=$$($(AWS) ssm get-parameter --name "/$(STACK_PREFIX)/triage/runtime-id" \
		--query "Parameter.Value" --output text 2>/dev/null) && \
	   [ "$$RUNTIME_ID" != "None" ] && [ -n "$$RUNTIME_ID" ]; then \
		echo "  [triage] Updating existing runtime: $$RUNTIME_ID" && \
		$(AWS) bedrock-agentcore-control update-agent-runtime \
			--agent-runtime-id "$$RUNTIME_ID" \
			--role-arn "$$ROLE_ARN" \
			--network-configuration '{"networkMode":"PUBLIC"}' \
			--agent-runtime-artifact "{\"containerConfiguration\":{\"containerUri\":\"$(TRIAGE_ECR_URI):$(TRIAGE_IMAGE_TAG)\"}}" \
			--environment-variables "$$ENV_VARS" > /dev/null ; \
	else \
		echo "  [triage] Creating new AgentCore Runtime..." && \
		RUNTIME_ID=$$($(AWS) bedrock-agentcore-control create-agent-runtime \
			--agent-runtime-name "$(TRIAGE_RUNTIME_NAME)" \
			--description "PULSE Triage Agent - async alert triage via shared StayOS Gateway" \
			--role-arn "$$ROLE_ARN" \
			--network-configuration '{"networkMode":"PUBLIC"}' \
			--agent-runtime-artifact "{\"containerConfiguration\":{\"containerUri\":\"$(TRIAGE_ECR_URI):$(TRIAGE_IMAGE_TAG)\"}}" \
			--environment-variables "$$ENV_VARS" \
			--query 'agentRuntimeId' --output text) && \
		$(AWS) ssm put-parameter --name "/$(STACK_PREFIX)/triage/runtime-id" \
			--value "$$RUNTIME_ID" --type String --overwrite > /dev/null && \
		echo "  [triage] Runtime created: $$RUNTIME_ID" ; \
	fi && \
	RUNTIME_ID=$$($(AWS) ssm get-parameter --name "/$(STACK_PREFIX)/triage/runtime-id" \
		--query "Parameter.Value" --output text) && \
	RUNTIME_ARN="arn:aws:bedrock-agentcore:$(REGION):$(ACCOUNT_ID):runtime/$$RUNTIME_ID" && \
	$(AWS) ssm put-parameter --name "$(TRIAGE_RUNTIME_SSM)" \
		--value "$$RUNTIME_ARN" --type String --overwrite > /dev/null && \
	echo "  [triage] Runtime ARN stored in SSM $(TRIAGE_RUNTIME_SSM):" && \
	echo "           $$RUNTIME_ARN" && \
	echo "  [triage] Thread it into the stack as TriageRuntimeArn on the next deploy."

# ─── Seed (post-deploy demo data) ─────────────────────────────
# Re-run the kitchen snapshot seed on demand. Kitchen seeding is a
# CloudFormation custom resource (pulse-data.yaml -> Custom::KitchenSeed) that
# runs automatically on `make deploy`; this target only re-invokes the seed
# Lambda directly for a manual refresh (mirrors LUMI's `make reseed`). The
# direct invoke sends no ResponseURL, so the handler skips the CFN response and
# just performs the idempotent put. Bump the KitchenSeedTrigger parameter on a
# deploy instead if you want CloudFormation to re-run it.
kitchen-reseed: ## Re-invoke the kitchen seed Lambda directly (manual refresh)
	@echo "Re-invoking $(STACK_PREFIX)-kitchen-seed Lambda (direct, no ResponseURL)..."
	@$(AWS) lambda invoke \
		--function-name $(STACK_PREFIX)-kitchen-seed \
		--cli-binary-format raw-in-base64-out \
		--payload '{"RequestType":"Create","ResourceProperties":{}}' \
		/tmp/pulse-kitchen-reseed.json > /dev/null
	@echo "Kitchen seed invoked; response: $$(cat /tmp/pulse-kitchen-reseed.json)"

# Run BOTH data seeds via direct Lambda invoke (no ResponseURL -> idempotent put,
# no CFN response). Used by `deploy` right after update-lambda-code so the real
# seed code runs against the real package (the first stack-create seeds ran as a
# no-op against the placeholder). Idempotent and safe to re-run.
seed-run: ## Invoke kitchen + rules seed Lambdas directly against real code
	@for SEED in kitchen-seed rules-seed; do \
		FN="$(STACK_PREFIX)-$$SEED"; \
		echo "  [seed] Invoking $$FN (direct, no ResponseURL)..."; \
		$(AWS) lambda invoke \
			--function-name "$$FN" \
			--cli-binary-format raw-in-base64-out \
			--payload '{"RequestType":"Create","ResourceProperties":{}}' \
			/tmp/pulse-$$SEED-run.json > /dev/null \
			&& echo "  [seed] $$FN response: $$(cat /tmp/pulse-$$SEED-run.json)" \
			|| { echo "  [seed] ERROR: $$FN invoke failed"; exit 1; }; \
	done
	@echo "PULSE data seeds complete."

# ─── Cleanup ──────────────────────────────────────────────────
clean: ## Remove build artifacts (build/, frontend out/.next, __pycache__)
	@rm -rf $(BUILD_DIR) $(FRONTEND_DIR)/out $(FRONTEND_DIR)/.next
	@find . -type d -name '__pycache__' -prune -exec rm -rf {} + 2>/dev/null || true
	@echo "Clean"
