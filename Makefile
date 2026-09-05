# Makefile — StayOS platform delegator
#
# This root Makefile does not build feature code itself. It delegates to each
# feature's own Makefile under <feature>/Makefile (so a contributor working on
# one feature never needs to know about the others), plus one cross-feature
# orchestration target — `deploy-all` — that deploys LUMI, captures its stack
# outputs, and threads them into the PULSE deploy (PULSE consumes LUMI's Cognito
# pool, DynamoDB stream ARNs, shared Gateway endpoint, and Tool Lambda ARN).
#
# Usage:
#   make help                # list available targets
#   make lumi-deploy          # -> make -C lumi deploy
#   make lumi-test            # -> make -C lumi test
#   make lumi-destroy         # -> make -C lumi destroy
#   make pulse-deploy         # -> make -C pulse deploy
#   make shell-deploy         # -> make -C stayos-shell deploy (publish the shell to /)
#   make deploy-all APP_PASSWORD=... [PROFILE=... REGION=...]   # LUMI then PULSE, wired
#   make test-all             # run every feature's test suite

# ─── Config (used only by deploy-all for cross-feature output threading) ──────
# Standalone feature deploys (make lumi-*/pulse-*) do not use these — they pass
# their own vars straight through the pattern rules below.
REGION            ?= us-east-1
# Profile: PULSE uses PROFILE, LUMI uses AWS_PROFILE. Accept either at the root
# so a caller can set whichever convention they know; PROFILE wins if both are
# set, otherwise AWS_PROFILE is used. deploy-all forwards the resolved value to
# each feature under the variable name that feature expects.
PROFILE           ?= $(AWS_PROFILE)
LUMI_STACK_PREFIX ?= stayos
# LUMI stack name mirrors lumi/Makefile: ${StackPrefix}-${Region}.
LUMI_STACK        := $(LUMI_STACK_PREFIX)-$(REGION)
AWS_PROFILE_FLAG  := $(if $(PROFILE),--profile $(PROFILE),)
AWS               := aws $(AWS_PROFILE_FLAG) --region $(REGION)
# APP_PASSWORD is required by `make deploy-all` (forwarded to LUMI's deploy).
APP_PASSWORD      ?=

.PHONY: help deploy-all test-all

help:
	@echo "StayOS platform Makefile — delegates to per-feature Makefiles."
	@echo ""
	@echo "  make lumi-<target>    run <target> in lumi/ (deploy, destroy, test, lint, reseed, ...)"
	@echo "  make pulse-<target>   run <target> in pulse/ (test, lint, validate, package, deploy, ...)"
	@echo "  make shell-<target>   run <target> in stayos-shell/ (test, lint, build-frontend, deploy, ...)"
	@echo "  make data-<target>    run <target> in shared/data-orchestrator/ (deploy, test, validate, destroy, ...)"
	@echo "  make deploy-all       deploy LUMI, then deploy PULSE with LUMI's outputs threaded in"
	@echo "                        requires APP_PASSWORD=...; honors PROFILE=... REGION=... (default us-east-1)"
	@echo "  make test-all         run every feature's test suite (shell + LUMI + PULSE + data-orchestrator)"
	@echo ""
	@echo "  The StayOS shell (login + launcher at /) publishes to the shared distribution root."
	@echo "  After LUMI's stack exists, run: make shell-deploy [PROFILE=... REGION=...]"
	@echo ""
	@echo "  The shared data orchestrator is deployed additively AFTER deploy-all:"
	@echo "  run: make data-deploy [AWS_PROFILE=... REGION=...] (does not re-seed live data)."
	@echo ""
	@echo "See lumi/Makefile and lumi/README.md for the full LUMI target list."

# Pattern rule: `make lumi-<anything>` forwards <anything> to `make -C lumi <anything>`.
# Same for pulse-<anything>. This mirrors the prefixed-target convention already
# used inside lumi/Makefile (voice-deploy, chat-deploy, gateway-deploy, ...).
# These standalone paths are unchanged: LUMI-only and PULSE-only deploys work as before.
lumi-%:
	$(MAKE) -C lumi $*

pulse-%:
	$(MAKE) -C pulse $*

# `make shell-<anything>` forwards to the StayOS shell Makefile. The shell is
# static assets published to the ROOT of the shared distribution (owned by LUMI),
# so shell-deploy should be run after LUMI's stack exists.
shell-%:
	$(MAKE) -C stayos-shell $*

# `make data-<anything>` forwards to the shared Unified Data Orchestrator
# Makefile under shared/data-orchestrator/ (e.g. data-deploy, data-test,
# data-validate, data-destroy). The orchestrator is a shared, cross-feature
# stack (StackPrefix stayos-data) that owns the per-property roll-forward layer
# and PULSE baseline priming. It is deployed ADDITIVELY (see its Makefile
# DESIGN NOTE): it does not take over initial seeding, so the legacy
# stayos-seed-data path and the live dataset are left untouched. It depends on
# LUMI/PULSE already being deployed, so run data-deploy after `make deploy-all`.
data-%:
	$(MAKE) -C shared/data-orchestrator $*

# ─── deploy-all: deploy both features, wiring LUMI's outputs into PULSE ───────
# PULSE cannot deploy standalone — it needs values produced by the LUMI deploy:
# the Cognito user pool (id/arn/client), the five operational-table DynamoDB
# stream ARNs, the shared AgentCore Gateway endpoint, and the shared Tool Lambda
# ARN. This target deploys LUMI, reads those back, and passes them into PULSE.
#
# Extraction mirrors the `Outputs[?OutputKey=='X'].OutputValue` pattern both
# feature Makefiles already use. The five stream ARNs are outputs of LUMI's
# nested DataStack (not the root stack), so we resolve DataStack's physical name
# via its fixed logical id and read them there. UserPoolArn is not exported, so
# it is derived deterministically from UserPoolId + region + account.
#
# WAF: PULSE associates a REGIONAL WAFv2 ACL to its API Gateway + AppSync Events
# API. LUMI's REGIONAL ACL (GatewayWafWebAclArn) is the correct one, but it is
# already associated with the shared AgentCore Gateway, so WAF is intentionally
# left unset here (it is optional in pulse/Makefile via the HasWaf condition).
# Pass WAF_WEB_ACL_ARN=<regional-acl-arn> to `make pulse-deploy` to enable it -
# do NOT pass LUMI's CLOUDFRONT-scope WebAclArn (scope mismatch fails).
#
# TRIAGE_RUNTIME_ARN is resolved automatically: deploy-all deploys the PULSE
# stack (pass 1), registers the Gateway tools, builds+deploys the Triage Agent
# AgentCore Runtime (writing its ARN to SSM /pulse/triage/runtime-arn), then
# re-deploys the PULSE stack (pass 2) threading that ARN so the rule evaluator
# can invoke it, and finally publishes the PULSE PWA to /pulse on the shared
# LUMI CloudFront. One command, end to end.
deploy-all:
	@if [ -z "$(APP_PASSWORD)" ]; then \
		echo ""; \
		echo "ERROR: APP_PASSWORD is required (it sets the LUMI demo GM login password)."; \
		echo "  make deploy-all APP_PASSWORD=your-secure-password [PROFILE=... REGION=...]"; \
		echo ""; \
		exit 1; \
	fi
	@echo "══ [1/6] Deploying LUMI ($(LUMI_STACK)) ══"
	@$(MAKE) -C lumi deploy APP_PASSWORD='$(APP_PASSWORD)' AWS_PROFILE='$(PROFILE)' REGION='$(REGION)'
	@echo ""
	@echo "══ [2/6] Capturing LUMI outputs and deploying the PULSE stack ══"
	@set -e; \
	out() { $(AWS) cloudformation describe-stacks --stack-name "$$1" \
		--query "Stacks[0].Outputs[?OutputKey=='$$2'].OutputValue" --output text; }; \
	USER_POOL_ID=$$(out $(LUMI_STACK) UserPoolId); \
	USER_POOL_CLIENT_ID=$$(out $(LUMI_STACK) UserPoolClientId); \
	TOOL_LAMBDA_ARN=$$(out $(LUMI_STACK) ToolLambdaArn); \
	ACCOUNT_ID=$$($(AWS) sts get-caller-identity --query Account --output text); \
	USER_POOL_ARN="arn:aws:cognito-idp:$(REGION):$$ACCOUNT_ID:userpool/$$USER_POOL_ID"; \
	GATEWAY_ENDPOINT_URL=$$($(AWS) ssm get-parameter \
		--name "/$(LUMI_STACK_PREFIX)/gateway/endpoint-url" \
		--query "Parameter.Value" --output text 2>/dev/null || echo ""); \
	DATA_STACK=$$($(AWS) cloudformation describe-stack-resources \
		--stack-name $(LUMI_STACK) --logical-resource-id DataStack \
		--query "StackResources[0].PhysicalResourceId" --output text); \
	RESERVATIONS_STREAM_ARN=$$(out $$DATA_STACK ReservationsStreamArn); \
	ROOMS_STREAM_ARN=$$(out $$DATA_STACK RoomsStreamArn); \
	GUESTS_STREAM_ARN=$$(out $$DATA_STACK GuestsStreamArn); \
	REVENUES_STREAM_ARN=$$(out $$DATA_STACK RevenuesStreamArn); \
	WORK_ORDERS_STREAM_ARN=$$(out $$DATA_STACK WorkOrdersStreamArn); \
	arn_of() { echo "$${1%%/stream/*}"; }; \
	RESERVATIONS_TABLE_ARN=$$(arn_of "$$RESERVATIONS_STREAM_ARN"); \
	ROOMS_TABLE_ARN=$$(arn_of "$$ROOMS_STREAM_ARN"); \
	GUESTS_TABLE_ARN=$$(arn_of "$$GUESTS_STREAM_ARN"); \
	REVENUES_TABLE_ARN=$$(arn_of "$$REVENUES_STREAM_ARN"); \
	WORK_ORDERS_TABLE_ARN=$$(arn_of "$$WORK_ORDERS_STREAM_ARN"); \
	tbl_name() { t="$${1##*:table/}"; echo "$${t%%/stream/*}"; }; \
	RESERVATIONS_TABLE_NAME=$$(tbl_name "$$RESERVATIONS_STREAM_ARN"); \
	ROOMS_TABLE_NAME=$$(tbl_name "$$ROOMS_STREAM_ARN"); \
	GUESTS_TABLE_NAME=$$(tbl_name "$$GUESTS_STREAM_ARN"); \
	echo "  Captured: UserPoolId=$$USER_POOL_ID  ToolLambdaArn=$$TOOL_LAMBDA_ARN"; \
	echo "  Streams:  reservations/rooms/guests/revenues/work-orders resolved from DataStack $$DATA_STACK"; \
	echo "  Tables:   $$RESERVATIONS_TABLE_ARN (+ rooms/guests/revenues/work-orders) derived for IAM scoping"; \
	pulse_deploy() { \
		$(MAKE) -C pulse deploy PROFILE='$(PROFILE)' REGION='$(REGION)' \
			USER_POOL_ID="$$USER_POOL_ID" \
			USER_POOL_ARN="$$USER_POOL_ARN" \
			USER_POOL_CLIENT_ID="$$USER_POOL_CLIENT_ID" \
			GATEWAY_ENDPOINT_URL="$$GATEWAY_ENDPOINT_URL" \
			RESERVATIONS_STREAM_ARN="$$RESERVATIONS_STREAM_ARN" \
			ROOMS_STREAM_ARN="$$ROOMS_STREAM_ARN" \
			GUESTS_STREAM_ARN="$$GUESTS_STREAM_ARN" \
			REVENUES_STREAM_ARN="$$REVENUES_STREAM_ARN" \
			WORK_ORDERS_STREAM_ARN="$$WORK_ORDERS_STREAM_ARN" \
			RESERVATIONS_TABLE_ARN="$$RESERVATIONS_TABLE_ARN" \
			ROOMS_TABLE_ARN="$$ROOMS_TABLE_ARN" \
			GUESTS_TABLE_ARN="$$GUESTS_TABLE_ARN" \
			REVENUES_TABLE_ARN="$$REVENUES_TABLE_ARN" \
			WORK_ORDERS_TABLE_ARN="$$WORK_ORDERS_TABLE_ARN" \
			RESERVATIONS_TABLE_NAME="$$RESERVATIONS_TABLE_NAME" \
			ROOMS_TABLE_NAME="$$ROOMS_TABLE_NAME" \
			GUESTS_TABLE_NAME="$$GUESTS_TABLE_NAME" \
			TRIAGE_RUNTIME_ARN="$$1"; \
	}; \
	pulse_deploy "" \
		|| { echo ""; \
		     echo "ERROR: PULSE stack deploy (pass 1) failed. LUMI ($(LUMI_STACK)) is already"; \
		     echo "deployed and healthy - do NOT redeploy it. Fix the error above, then re-run"; \
		     echo "  make deploy-all APP_PASSWORD=... PROFILE=$(PROFILE) REGION=$(REGION)"; \
		     echo ""; exit 1; }; \
	echo ""; \
	echo "══ [3/6] Registering PULSE tools on the shared StayOS Gateway ══"; \
	$(MAKE) -C pulse gateway-deploy PROFILE='$(PROFILE)' REGION='$(REGION)' \
		TOOL_LAMBDA_ARN="$$TOOL_LAMBDA_ARN" \
		|| { echo ""; \
		     echo "ERROR: PULSE Gateway tool registration failed. Both stacks are deployed."; \
		     echo "Re-run only this step: make pulse-gateway-deploy PROFILE=$(PROFILE) REGION=$(REGION) TOOL_LAMBDA_ARN=$$TOOL_LAMBDA_ARN"; \
		     echo ""; exit 1; }; \
	echo ""; \
	echo "══ [4/6] Building the Triage Agent runtime, then re-deploying PULSE with its ARN ══"; \
	$(MAKE) -C pulse triage-deploy PROFILE='$(PROFILE)' REGION='$(REGION)' \
		|| { echo ""; \
		     echo "ERROR: Triage Agent build/deploy failed (CodeBuild or AgentCore). Both stacks"; \
		     echo "are deployed; alerts are created but agentic triage will not fire until this"; \
		     echo "succeeds. Re-run: make pulse-triage-deploy PROFILE=$(PROFILE) REGION=$(REGION)"; \
		     echo ""; exit 1; }; \
	TRIAGE_RUNTIME_ARN=$$($(AWS) ssm get-parameter \
		--name "/pulse/triage/runtime-arn" \
		--query "Parameter.Value" --output text 2>/dev/null || echo ""); \
	if [ -z "$$TRIAGE_RUNTIME_ARN" ]; then \
		echo "ERROR: Triage runtime ARN not found in SSM after triage-deploy."; exit 1; \
	fi; \
	echo "  Re-deploying PULSE stack with TriageRuntimeArn=$$TRIAGE_RUNTIME_ARN"; \
	pulse_deploy "$$TRIAGE_RUNTIME_ARN" \
		|| { echo ""; \
		     echo "ERROR: PULSE stack re-deploy (pass 2, with triage ARN) failed. The runtime"; \
		     echo "exists (SSM /pulse/triage/runtime-arn); re-run: make deploy-all ... to retry."; \
		     echo ""; exit 1; }; \
	echo ""; \
	echo "══ [5/6] Publishing the PULSE PWA to /pulse on the shared LUMI CloudFront ══"; \
	$(MAKE) -C pulse deploy-frontend PROFILE='$(PROFILE)' REGION='$(REGION)' \
		USER_POOL_CLIENT_ID="$$USER_POOL_CLIENT_ID" \
		COGNITO_REGION='$(REGION)' \
		|| { echo ""; \
		     echo "ERROR: PULSE frontend publish failed. Backend is fully deployed."; \
		     echo "Re-run only this step: make pulse-deploy-frontend PROFILE=$(PROFILE) REGION=$(REGION) USER_POOL_CLIENT_ID=<id>"; \
		     echo ""; exit 1; }; \
	echo ""; \
	echo "══ [6/6] Deploying the shared Data Orchestrator (roll-forward + baseline) ══"; \
	$(MAKE) -C shared/data-orchestrator deploy AWS_PROFILE='$(PROFILE)' REGION='$(REGION)' \
		LUMI_STACK_PREFIX='$(LUMI_STACK_PREFIX)' PULSE_STACK_PREFIX='pulse' \
		|| { echo ""; \
		     echo "ERROR: Data Orchestrator deploy failed. LUMI + PULSE are fully deployed"; \
		     echo "and healthy - do NOT redeploy them. The orchestrator is additive (it does"; \
		     echo "not re-seed live data). Re-run only this step:"; \
		     echo "  make data-deploy AWS_PROFILE=$(PROFILE) REGION=$(REGION) LUMI_STACK_PREFIX=$(LUMI_STACK_PREFIX)"; \
		     echo ""; exit 1; }
	@echo ""
	@echo "════════════════════════════════════════════════════════════════"
	@echo "  StayOS deployed end to end: LUMI + PULSE + Data Orchestrator"
	@echo "  (stack, triage, frontend, and the additive roll-forward layer)."
	@echo "  PULSE PWA: <lumi-cloudfront-domain>/pulse/"
	@echo "════════════════════════════════════════════════════════════════"

test-all: shell-test lumi-test pulse-test data-test

