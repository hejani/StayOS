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

# The six step-Lambda handlers + starters all live in handlers/ and are bundled
# into one zip. AWS profile flag threaded into every aws call.
AWS_PROFILE_FLAG := $(if $(AWS_PROFILE),--profile $(AWS_PROFILE),)
AWS := aws $(AWS_PROFILE_FLAG) --region $(REGION)

.PHONY: all deploy package ensure-bucket package-infra deploy-infra \
        update-lambda-code validate test lint clean destroy

# ─── Full Deploy (single command) ─────────────────────────────
all: deploy

deploy: ensure-bucket package deploy-infra update-lambda-code
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
	@echo "  live dataset is untouched. Roll-forward schedules run per property"
	@echo "  at local midnight in their own schedule group."
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
# S3Key with a distinct Handler). No third-party deps: the handlers use only
# boto3/stdlib (present in the python3.12 runtime); the dataset_generator_shim
# adds the LUMI generator path at runtime, so no dependency layer is built.
package:
	@echo "[2/4] Packaging orchestrator Lambda (all handlers in one zip)..."
	@mkdir -p build
	@cd handlers && zip -r ../build/data-orchestrator.zip . \
		-x "*.pyc" "__pycache__/*" ".mypy_cache/*" ".pytest_cache/*" ".ruff_cache/*" "*.dist-info/*" > /dev/null
	@$(AWS) s3 cp build/data-orchestrator.zip s3://$(DEPLOY_BUCKET)/$(LAMBDA_S3_KEY) --quiet
	@echo "    done"

# ─── Step 3: Deploy the CloudFormation stack ──────────────────
# StackPrefix=stayos-data; DeployBucket/LambdaCodeS3Key point CloudFormation at
# the artifact packaged above. Seed Lambda ARNs are passed through (empty by
# default for Option 1). CAPABILITY_NAMED_IAM: the template creates named IAM
# roles with the AWS::Region suffix.
deploy-infra:
	@echo "[3/4] Deploying orchestrator stack (this may take a few minutes)..."
	@$(AWS) cloudformation deploy \
		--stack-name $(STACK_NAME) \
		--template-file infrastructure/data-orchestrator.yaml \
		--parameter-overrides \
			StackPrefix=$(STACK_PREFIX) \
			DeployBucket=$(DEPLOY_BUCKET) \
			LambdaCodeS3Key=$(LAMBDA_S3_KEY) \
			SeedTrigger=$(SEED_TRIGGER) \
			LumiSeedLambdaArn=$(LUMI_SEED_LAMBDA_ARN) \
			PulseSeedLambdaArn=$(PULSE_SEED_LAMBDA_ARN) \
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
