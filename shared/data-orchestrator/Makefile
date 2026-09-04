# Makefile — StayOS Unified Data Orchestrator (shared) Build & Deploy
#
# Packages the single orchestrator Lambda deployment zip (all step handlers +
# orchestrator_common share one artifact; each Lambda in the template points at
# the same S3Key with a different Handler), uploads it, and deploys the
# stayos-data-orchestrator CloudFormation stack.
#
# DESIGN NOTE (Option 1 — additive):
#   This deploy is ADDITIVE. It stands up the shared orchestrator alongside the
#   existing LUMI/PULSE deployments to own the per-property roll-forward layer
#   and PULSE baseline priming ONLY. It does NOT take over initial seeding:
#   LumiSeedLambdaArn / PulseSeedLambdaArn are left empty (their template
#   defaults), which disables the orchestrator's application-data seed path, so
#   the existing legacy stayos-seed-data custom resource remains the initial
#   seeder and the live dataset is never re-seeded or bulk-rewritten by this
#   stack. The orchestrator's roll-forward schedules live in their own schedule
#   group (distinct from LUMI's stayos-briefs), so they cannot touch the
#   GM-customized brief-delivery schedules.
#
# Prerequisites: AWS CLI v2, Python 3.12, zip.
# Usage:
#   make deploy                          # uses current AWS profile account
#   make deploy AWS_PROFILE=my-profile   # explicit profile
#   make validate                        # cfn-lint-free template validation (no deploy)
#   make test                            # run the orchestrator unit/integration tests
#   make destroy                         # tear down the orchestrator stack

# ─── Config ───────────────────────────────────────────────────
# StackPrefix matches the template default (data-orchestrator.yaml) and the
# repo NAMING convention for the shared orchestrator: stayos-data.
STACK_PREFIX ?= stayos-data
AWS_PROFILE ?=
export AWS_PROFILE
ACCOUNT_ID ?= $(shell AWS_PROFILE=$(AWS_PROFILE) aws sts get-caller-identity --query Account --output text 2>/dev/null)
REGION ?= $(shell AWS_PROFILE=$(AWS_PROFILE) aws configure get region 2>/dev/null || echo us-east-1)
# Stack name mirrors the LUMI/PULSE convention: ${StackPrefix}-${Region}.
STACK_NAME := $(STACK_PREFIX)-$(REGION)
# Reuse LUMI's deploy bucket (${LumiStackPrefix}-deploy-${AccountId}) so we do
# not create a second artifacts bucket for one small zip. Override DEPLOY_BUCKET
# to use a different bucket.
LUMI_STACK_PREFIX ?= stayos
DEPLOY_BUCKET ?= $(LUMI_STACK_PREFIX)-deploy-$(ACCOUNT_ID)
LAMBDA_S3_KEY := functions/data-orchestrator.zip

# ─── Option 1 knobs (additive deploy) ─────────────────────────
# Left empty on purpose: empty disables the orchestrator's application/PULSE
# seed path (see DESIGN NOTE above). Set these only for a future full cutover.
LUMI_SEED_LAMBDA_ARN ?=
PULSE_SEED_LAMBDA_ARN ?=
# Bump to force the first-deploy seed custom resource to re-run (idempotent
# upsert-only). Kept at the template default for an additive deploy.
SEED_TRIGGER ?= 1

# ─── LUMI resource names threaded into the orchestrator (AI-1/AI-2/AI-3) ──────
# The Generate/Reconcile/RegenerateBrief steps target the live LUMI operational
# tables + settings + orchestrator. Derived from the LUMI StackPrefix so they
# follow whatever LUMI is deployed as (today stayos-*). Overridable.
LUMI_RESERVATIONS_TABLE ?= $(LUMI_STACK_PREFIX)-reservations
LUMI_ROOMS_TABLE        ?= $(LUMI_STACK_PREFIX)-rooms
LUMI_GUESTS_TABLE       ?= $(LUMI_STACK_PREFIX)-guests
LUMI_REVENUES_TABLE     ?= $(LUMI_STACK_PREFIX)-revenues
LUMI_WORK_ORDERS_TABLE  ?= $(LUMI_STACK_PREFIX)-work-orders
LUMI_SETTINGS_TABLE     ?= $(LUMI_STACK_PREFIX)-settings
LUMI_ORCHESTRATOR_FN    ?= $(LUMI_STACK_PREFIX)-orchestrator

# PULSE rule-evaluator function whose DynamoDB-stream ESMs the Quiesce step
# toggles (AI-4). Derived from the PULSE StackPrefix. The ESM UUIDs are resolved
# LIVE at deploy time (they change on PULSE redeploy) - see the deploy target.
PULSE_STACK_PREFIX      ?= pulse
PULSE_RULE_EVALUATOR_FN ?= $(PULSE_STACK_PREFIX)-rule-evaluator

# Pilot estate (matches the template EstatePropertyIds default). Used by the
# post-deploy `prime` step to generate today's brief for every property so a
# fresh deploy is populated out of the box (no waiting for local midnight).
ESTATE_PROPERTY_IDS ?= ALOHA-CHI-001 ALOHA-MIA-001 ALOHA-TYO-001 ALOHA-MAD-001 ALOHA-BOM-001

# The six step-Lambda handlers + starters all live in handlers/ and are bundled
# into one zip. AWS profile flag threaded into every aws call.
AWS_PROFILE_FLAG := $(if $(AWS_PROFILE),--profile $(AWS_PROFILE),)
AWS := aws $(AWS_PROFILE_FLAG) --region $(REGION)

.PHONY: all deploy package ensure-bucket package-infra deploy-infra \
        update-lambda-code prime validate test lint clean destroy

# ─── Full Deploy (single command) ─────────────────────────────
all: deploy

deploy: ensure-bucket package deploy-infra update-lambda-code prime
	@echo ""
	@echo "══════════════════════════════════════════════════════════════"
	@echo "  Data Orchestrator deployment complete (additive / Option 1)"
	@echo ""
	@echo "  Stack:    $(STACK_NAME)"
	@echo "  Account:  $(ACCOUNT_ID)"
	@echo "  Region:   $(REGION)"
	@echo ""
	@echo "  State machine: $$($(AWS) cloudformation describe-stacks \
		--stack-name $(STACK_NAME) \
		--query "Stacks[0].Outputs[?OutputKey=='StateMachineArn'].OutputValue" \
		--output text 2>/dev/null)"
	@echo ""
	@echo "  Seeding is DISABLED (LumiSeedLambdaArn/PulseSeedLambdaArn empty):"
	@echo "  the legacy stayos-seed-data path remains the initial seeder and the"
	@echo "  live dataset is untouched. Today's brief for every property was"
	@echo "  primed by the roll-forward above; thereafter the per-property"
	@echo "  local-midnight schedules keep them fresh (own schedule group)."
	@echo "══════════════════════════════════════════════════════════════"

# ─── Step 1: Ensure the deploy bucket exists ──────────────────
# Reuses LUMI's deploy bucket by default; create it only if missing.
ensure-bucket:
	@echo "[1/4] Ensuring deploy bucket exists ($(DEPLOY_BUCKET))..."
	@$(AWS) s3api head-bucket --bucket $(DEPLOY_BUCKET) 2>/dev/null || \
		$(AWS) s3 mb s3://$(DEPLOY_BUCKET) > /dev/null
	@echo "    done"

# ─── Step 2: Package the orchestrator Lambda zip ──────────────
# All handlers share one artifact (the template gives each Lambda the same
# S3Key with a distinct Handler). The handlers depend on aws-lambda-powertools
# (Logger) per the repo PYQUALITY rules; it is NOT in the base Lambda runtime,
# so it is vendored directly into the zip (pip install -t) alongside the handler
# modules. All other imports are boto3/stdlib (present in the python3.12
# runtime); the dataset_generator_shim adds the LUMI generator path at runtime.
#
# QUIESCE SEAM (AI-4): the Quiesce/UnQuiesce steps import the PULSE-owned seam
# `pulse.rule_engine.quiesce` via pulse_quiesce_shim. For that import to resolve
# at runtime the PULSE `pulse` package must be on the path, so we vendor it into
# the zip (the shim also honors PULSE_BACKEND_SRC_PATH). Without this the seam is
# unavailable and quiesce degrades to a no-op even when ESM UUIDs are set.
PULSE_BACKEND_SRC := ../../pulse/backend/src
LUMI_SEED_DATA_SRC := ../../lumi/backend/functions/seed-data
package:
	@echo "[2/4] Packaging orchestrator Lambda (handlers + deps + generators + quiesce seam)..."
	@rm -rf build && mkdir -p build/pkg
	@cp handlers/*.py build/pkg/
	@pip3 install -r requirements.txt -t build/pkg/ \
		--quiet --disable-pip-version-check
	@# Vendor the LUMI dataset_generator package so `import dataset_generator`
	@# (via dataset_generator_shim) resolves at runtime - Generate/Reconcile reuse it.
	@if [ -d "$(LUMI_SEED_DATA_SRC)/dataset_generator" ]; then \
		cp -R "$(LUMI_SEED_DATA_SRC)/dataset_generator" build/pkg/dataset_generator; \
	else \
		echo "    ERROR: LUMI dataset_generator not found at $(LUMI_SEED_DATA_SRC)"; exit 1; \
	fi
	@# Vendor the PULSE `pulse` package so the quiesce seam import resolves.
	@if [ -d "$(PULSE_BACKEND_SRC)/pulse" ]; then \
		cp -R "$(PULSE_BACKEND_SRC)/pulse" build/pkg/pulse; \
	else \
		echo "    WARNING: PULSE package not found at $(PULSE_BACKEND_SRC)/pulse - quiesce will no-op"; \
	fi
	@cd build/pkg && zip -r ../data-orchestrator.zip . \
		-x "*.pyc" "__pycache__/*" "*.dist-info/*" "*.egg-info/*" "*/tests/*" "tests/*" > /dev/null
	@$(AWS) s3 cp build/data-orchestrator.zip s3://$(DEPLOY_BUCKET)/$(LAMBDA_S3_KEY) --quiet
	@echo "    done"

# ─── Step 3: Deploy the CloudFormation stack ──────────────────
# StackPrefix=stayos-data; DeployBucket/LambdaCodeS3Key point CloudFormation at
# the artifact packaged above. Seed Lambda ARNs are passed through (empty by
# default for Option 1). The LUMI table/settings/orchestrator names and the live
# PULSE rule-evaluator ESM UUIDs (resolved below) are threaded in so the
# Generate/Reconcile/RegenerateBrief/Quiesce steps target the real resources.
# CAPABILITY_NAMED_IAM: the template creates named IAM roles with the Region suffix.
deploy-infra:
	@echo "[3/4] Deploying orchestrator stack (this may take a few minutes)..."
	@# Resolve the live PULSE rule-evaluator ESM UUIDs (AI-4). They change on a
	@# PULSE redeploy, so query them now rather than hardcoding. Empty (PULSE not
	@# deployed / no mappings) → quiesce safely no-ops.
	@ESM_UUIDS=$$($(AWS) lambda list-event-source-mappings \
		--function-name $(PULSE_RULE_EVALUATOR_FN) \
		--query "EventSourceMappings[].UUID" --output text 2>/dev/null | tr '\t' ',' || echo ""); \
	echo "    rule-evaluator ESM UUIDs: $${ESM_UUIDS:-<none - quiesce no-ops>}"; \
	$(AWS) cloudformation deploy \
		--stack-name $(STACK_NAME) \
		--template-file infrastructure/data-orchestrator.yaml \
		--parameter-overrides \
			StackPrefix=$(STACK_PREFIX) \
			DeployBucket=$(DEPLOY_BUCKET) \
			LambdaCodeS3Key=$(LAMBDA_S3_KEY) \
			SeedTrigger=$(SEED_TRIGGER) \
			LumiSeedLambdaArn=$(LUMI_SEED_LAMBDA_ARN) \
			PulseSeedLambdaArn=$(PULSE_SEED_LAMBDA_ARN) \
			ReservationsTableName=$(LUMI_RESERVATIONS_TABLE) \
			RoomsTableName=$(LUMI_ROOMS_TABLE) \
			GuestsTableName=$(LUMI_GUESTS_TABLE) \
			RevenuesTableName=$(LUMI_REVENUES_TABLE) \
			WorkOrdersTableName=$(LUMI_WORK_ORDERS_TABLE) \
			SettingsTableName=$(LUMI_SETTINGS_TABLE) \
			LumiOrchestratorFunctionName=$(LUMI_ORCHESTRATOR_FN) \
			RuleEngineEsmUuids="$$ESM_UUIDS" \
		--capabilities CAPABILITY_NAMED_IAM CAPABILITY_AUTO_EXPAND \
		--no-fail-on-empty-changeset
	@echo "    done"

# ─── Step 4: Force Lambda code refresh ────────────────────────
# CloudFormation keys Lambda code by a static S3 key, so it cannot see when the
# zip content changes. Force an update on each step/starter Lambda so the latest
# handler code is always running after a deploy. Failures are tolerated (a
# function may not exist yet on the very first create).
update-lambda-code:
	@echo "[4/4] Refreshing Lambda function code..."
	@for fn in quiesce generate reconcile unquiesce regenerate-brief prime-baseline seed-starter rollforward-starter; do \
		$(AWS) lambda update-function-code \
			--function-name $(STACK_PREFIX)-$$fn \
			--s3-bucket $(DEPLOY_BUCKET) \
			--s3-key $(LAMBDA_S3_KEY) > /dev/null 2>&1 || true; \
	done
	@sleep 3
	@echo "    done"

# ─── Post-deploy: prime today's data for every property ───────
# A fresh deploy's seeded window is anchored to a reference date that may not be
# the current calendar date, so a brief for "today" may not exist until the
# per-property local-midnight schedule fires. This step runs an immediate
# roll-forward for every pilot property so the app is populated out of the box
# (LUMI briefs for today + re-anchored window). It is:
#   - idempotent: roll-forward is upsert-only and the concurrency guard skips a
#     duplicate same-property/day execution (ExecutionAlreadyExists);
#   - failure-isolated: a property that fails to prime logs a warning but does
#     not fail the deploy (the nightly schedule will still catch it up).
# Waits briefly for each execution so a following step sees populated data.
prime:
	@echo "[5/5] Priming today's data for the estate (per-property roll-forward)..."
	@SM=$$($(AWS) cloudformation describe-stacks --stack-name $(STACK_NAME) \
		--query "Stacks[0].Outputs[?OutputKey=='StateMachineArn'].OutputValue" \
		--output text 2>/dev/null); \
	if [ -z "$$SM" ] || [ "$$SM" = "None" ]; then \
		echo "    WARNING: state machine ARN not found; skipping prime"; \
	else \
		EXECS=""; \
		for P in $(ESTATE_PROPERTY_IDS); do \
			E=$$($(AWS) stepfunctions start-execution --state-machine-arn "$$SM" \
				--name "prime-$$P-$$(date -u +%Y%m%dT%H%M%S)" \
				--input "{\"mode\":\"roll-forward\",\"propertyId\":\"$$P\"}" \
				--query "executionArn" --output text 2>/dev/null); \
			if [ -n "$$E" ] && [ "$$E" != "None" ]; then \
				echo "    started roll-forward for $$P"; EXECS="$$EXECS $$E"; \
			else \
				echo "    WARNING: could not start roll-forward for $$P (nightly schedule will catch up)"; \
			fi; \
		done; \
		for E in $$EXECS; do \
			for i in $$(seq 1 30); do \
				S=$$($(AWS) stepfunctions describe-execution --execution-arn "$$E" \
					--query "status" --output text 2>/dev/null); \
				case "$$S" in \
					SUCCEEDED) break;; \
					FAILED|TIMED_OUT|ABORTED) \
						echo "    WARNING: prime execution ended $$S (nightly schedule will catch up)"; break;; \
					*) sleep 6;; \
				esac; \
			done; \
		done; \
		echo "    done"; \
	fi

# ─── Template validation (no deploy) ──────────────────────────
# Validates the template with CloudFormation's validator. This does not create
# or change any resources.
validate:
	@echo "Validating orchestrator template..."
	@$(AWS) cloudformation validate-template \
		--template-body file://infrastructure/data-orchestrator.yaml > /dev/null
	@echo "Template is valid."

# ─── Testing ──────────────────────────────────────────────────
# Runs the orchestrator handler unit + integration tests (moto-mocked; no AWS
# calls). Note python3 (not python) per repo convention.
test:
	@echo "Running data-orchestrator tests..."
	@python3 -m pytest tests/ -v

lint:
	@echo "Linting orchestrator handlers..."
	@python3 -m ruff check handlers/ tests/

# ─── Cleanup ──────────────────────────────────────────────────
clean:
	@rm -rf build

# ─── Destroy ──────────────────────────────────────────────────
# Tears down the orchestrator stack ONLY. This does not touch LUMI, PULSE, or
# any operational data — the orchestrator holds no tables and (in Option 1) does
# not own the seed. Destructive: requires the caller to run it deliberately.
destroy:
	@echo "Deleting orchestrator stack $(STACK_NAME)..."
	@$(AWS) cloudformation delete-stack --stack-name $(STACK_NAME)
	@echo "Waiting for stack deletion to complete..."
	@$(AWS) cloudformation wait stack-delete-complete --stack-name $(STACK_NAME)
	@echo "Orchestrator stack deleted."
