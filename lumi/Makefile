# Makefile — LUMI Build & Deploy
# Handles bucket creation, backend packaging, infra deploy, frontend
# env generation, frontend build, S3 sync, and CDN invalidation.
#
# Prerequisites: AWS CLI v2, Python 3.12, Node.js 18+, zip, md5sum/md5
# Usage:
#   make deploy                         # uses current AWS profile account
#   make deploy ACCOUNT_ID=123456789012 # explicit account

STACK_PREFIX ?= stayos
AWS_PROFILE ?=
export AWS_PROFILE
ACCOUNT_ID ?= $(shell AWS_PROFILE=$(AWS_PROFILE) aws sts get-caller-identity --query Account --output text 2>/dev/null)
REGION ?= $(shell AWS_PROFILE=$(AWS_PROFILE) aws configure get region 2>/dev/null || echo us-east-1)
STACK_NAME := $(STACK_PREFIX)-$(REGION)
DEPLOY_BUCKET := $(STACK_PREFIX)-deploy-$(ACCOUNT_ID)
FRONTEND_BUCKET := $(STACK_PREFIX)-frontend-$(ACCOUNT_ID)
BEDROCK_MODEL_ID ?= us.anthropic.claude-sonnet-4-6
APP_PASSWORD ?=

.PHONY: all deploy ensure-buckets package-backend build-layer package-infra \
        deploy-infra update-lambda-code write-frontend-env build-frontend \
        deploy-frontend invalidate-cdn preflight clean test lint \
        test-backend test-frontend \
        voice-build voice-deploy voice-destroy reseed \
        gateway-deploy gateway-destroy \
        chat-build chat-deploy chat-destroy

# ─── Full Deploy (single command) ─────────────────────────────
all: deploy

deploy: preflight ensure-buckets package-backend deploy-infra update-lambda-code gateway-deploy voice-deploy chat-deploy write-frontend-env build-frontend deploy-frontend invalidate-cdn generate-briefs
	@echo ""
	@echo "══════════════════════════════════════════════════════════════"
	@echo "  LUMI deployment complete"
	@echo ""
	@echo "  Stack:    $(STACK_NAME)"
	@echo "  Account:  $(ACCOUNT_ID)"
	@echo "  Region:   $(REGION)"
	@echo ""
	@echo "  Frontend: $$(aws cloudformation describe-stacks \
		--stack-name $(STACK_NAME) \
		--query "Stacks[0].Outputs[?OutputKey=='FrontendUrl'].OutputValue" \
		--output text 2>/dev/null)"
	@echo "══════════════════════════════════════════════════════════════"

# ─── Pre-flight: Verify Bedrock model access ─────────────────
preflight:
	@if [ -z "$(APP_PASSWORD)" ]; then \
		echo ""; \
		echo "ERROR: APP_PASSWORD is not set."; \
		echo ""; \
		echo "This password protects the LUMI application login."; \
		echo "Set it in your environment or pass it to make:"; \
		echo ""; \
		echo "  export APP_PASSWORD=your-secure-password"; \
		echo "  make deploy"; \
		echo ""; \
		echo "  — or —"; \
		echo ""; \
		echo "  make deploy APP_PASSWORD=your-secure-password"; \
		echo ""; \
		exit 1; \
	fi
	@echo "[0/8] Verifying AWS CLI has bedrock-agentcore-control support..."
	@aws bedrock-agentcore-control list-gateways --region $(REGION) > /dev/null 2>&1 \
	|| (echo "" && \
		echo "ERROR: AWS CLI does not support 'bedrock-agentcore-control'." && \
		echo "" && \
		echo "This subcommand requires AWS CLI version 2.27 or later." && \
		echo "" && \
		echo "To update your AWS CLI:" && \
		echo "" && \
		echo "  macOS:  brew upgrade awscli" && \
		echo "  Linux:  curl 'https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip' -o 'awscliv2.zip' && unzip awscliv2.zip && sudo ./aws/install --update" && \
		echo "" && \
		echo "  Verify: aws --version" && \
		echo "" && \
		exit 1)
	@echo "    done"
	@echo "[0/8] Verifying Bedrock model access ($(BEDROCK_MODEL_ID))..."
	@aws bedrock-runtime converse \
		--model-id $(BEDROCK_MODEL_ID) \
		--messages '[{"role":"user","content":[{"text":"hi"}]}]' \
		--inference-config '{"maxTokens":1}' \
		--region $(REGION) > /dev/null 2>&1 \
	|| (echo "" && \
		echo "ERROR: Bedrock model $(BEDROCK_MODEL_ID) is not accessible." && \
		echo "" && \
		echo "To enable it, follow these steps:" && \
		echo "" && \
		echo "  1. Open the AWS Console in region $(REGION):" && \
		echo "     https://$(REGION).console.aws.amazon.com/bedrock/home?region=$(REGION)#/modelaccess" && \
		echo "" && \
		echo "  2. Click 'Manage model access' (top right)" && \
		echo "" && \
		echo "  3. Check the box next to 'Anthropic Claude Sonnet 4.6'" && \
		echo "     (under Anthropic > Claude)" && \
		echo "" && \
		echo "  4. Click 'Save changes' and wait for status to show 'Access granted'" && \
		echo "     (typically takes 1-2 minutes)" && \
		echo "" && \
		echo "  5. Re-run: make deploy" && \
		echo "" && \
		echo "Note: If your account uses an AWS Organization, model access may" && \
		echo "require approval from your org administrator." && \
		echo "" && \
		exit 1)
	@echo "    done"
	@echo "[0/8] Verifying Bedrock model access (amazon.nova-2-sonic-v1:0)..."
	@aws bedrock get-foundation-model \
		--model-identifier amazon.nova-2-sonic-v1:0 \
		--region $(REGION) > /dev/null 2>&1 \
	|| (echo "" && \
		echo "ERROR: Amazon Nova Sonic (amazon.nova-2-sonic-v1:0) is not accessible." && \
		echo "" && \
		echo "To enable it, follow these steps:" && \
		echo "" && \
		echo "  1. Open the AWS Console in region $(REGION):" && \
		echo "     https://$(REGION).console.aws.amazon.com/bedrock/home?region=$(REGION)#/modelaccess" && \
		echo "" && \
		echo "  2. Click 'Manage model access' (top right)" && \
		echo "" && \
		echo "  3. Check the box next to 'Amazon Nova Sonic'" && \
		echo "     (under Amazon > Nova)" && \
		echo "" && \
		echo "  4. Click 'Save changes' and wait for status to show 'Access granted'" && \
		echo "     (typically takes 1-2 minutes)" && \
		echo "" && \
		echo "  5. Re-run: make deploy" && \
		echo "" && \
		echo "Note: If your account uses an AWS Organization, model access may" && \
		echo "require approval from your org administrator." && \
		echo "" && \
		exit 1)
	@echo "    done"

# ─── Step 1: Ensure S3 buckets exist ──────────────────────────
ensure-buckets:
	@echo "[1/8] Creating S3 buckets (if needed)..."
	@aws s3api head-bucket --bucket $(DEPLOY_BUCKET) 2>/dev/null || \
		aws s3 mb s3://$(DEPLOY_BUCKET) --region $(REGION) > /dev/null
	@echo "    done"

# ─── Step 2: Package backend ──────────────────────────────────
build-layer:
	@cd backend/layers/dependencies && \
		pip3 install -r requirements.txt -t python/lib/python3.12/site-packages/ --quiet --disable-pip-version-check 2>/dev/null && \
		zip -r ../../../build/stayos-dependencies-layer.zip python/ -x "*.pyc" > /dev/null

package-backend: build-layer
	@echo "[2/8] Packaging backend..."
	@mkdir -p build
	@cd backend/functions/api && zip -r ../../../build/stayos-api.zip . -x "*.pyc" "__pycache__/*" > /dev/null
	@cd backend/functions/orchestrator && zip -r ../../../build/stayos-orchestrator.zip . -x "*.pyc" "__pycache__/*" > /dev/null
	@cd backend/functions/seed-data && zip -r ../../../build/stayos-seed-data.zip . -x "*.pyc" "__pycache__/*" > /dev/null
	@cd backend/functions/tools && zip -r ../../../build/stayos-tools.zip . -x "*.pyc" "__pycache__/*" > /dev/null
	@aws s3 cp build/stayos-dependencies-layer.zip s3://$(DEPLOY_BUCKET)/layers/ --quiet
	@aws s3 cp build/stayos-api.zip s3://$(DEPLOY_BUCKET)/functions/ --quiet
	@aws s3 cp build/stayos-orchestrator.zip s3://$(DEPLOY_BUCKET)/functions/ --quiet
	@aws s3 cp build/stayos-seed-data.zip s3://$(DEPLOY_BUCKET)/functions/ --quiet
	@aws s3 cp build/stayos-tools.zip s3://$(DEPLOY_BUCKET)/functions/ --quiet
	@echo "    done"

# ─── Step 3: Deploy infrastructure ────────────────────────────
package-infra:
	@aws cloudformation package \
		--template-file infrastructure/root-stack.yaml \
		--s3-bucket $(DEPLOY_BUCKET) \
		--s3-prefix cfn-templates \
		--output-template-file build/packaged-root-stack.yaml > /dev/null

deploy-infra: package-infra
	@echo "[3/8] Deploying infrastructure (this may take several minutes)..."
	@aws cloudformation deploy \
		--stack-name $(STACK_NAME) \
		--template-file build/packaged-root-stack.yaml \
		--parameter-overrides \
			StackPrefix=$(STACK_PREFIX) \
			AccountId=$(ACCOUNT_ID) \
			BedrockModelId=$(BEDROCK_MODEL_ID) \
			AppPassword=$(APP_PASSWORD) \
		--capabilities CAPABILITY_NAMED_IAM CAPABILITY_AUTO_EXPAND \
		--no-fail-on-empty-changeset
	@echo "    done"

# ─── Step 4: Update Lambda code ───────────────────────────────
# CloudFormation uses a static S3 key for Lambda code, so it cannot
# detect when the zip content changes. This step forces a code update
# on all Lambda functions after every deploy to ensure the latest code
# is always running.
update-lambda-code:
	@echo "[4/8] Updating Lambda function code..."
	@aws lambda update-function-code \
		--function-name $(STACK_PREFIX)-api \
		--s3-bucket $(DEPLOY_BUCKET) \
		--s3-key functions/stayos-api.zip \
		--region $(REGION) > /dev/null 2>&1 || true
	@aws lambda update-function-code \
		--function-name $(STACK_PREFIX)-orchestrator \
		--s3-bucket $(DEPLOY_BUCKET) \
		--s3-key functions/stayos-orchestrator.zip \
		--region $(REGION) > /dev/null 2>&1 || true
	@aws lambda update-function-code \
		--function-name $(STACK_PREFIX)-seed-data \
		--s3-bucket $(DEPLOY_BUCKET) \
		--s3-key functions/stayos-seed-data.zip \
		--region $(REGION) > /dev/null 2>&1 || true
	@aws lambda update-function-code \
		--function-name $(STACK_PREFIX)-tools \
		--s3-bucket $(DEPLOY_BUCKET) \
		--s3-key functions/stayos-tools.zip \
		--region $(REGION) > /dev/null 2>&1 || true
	@sleep 3
	@echo "    done"

# ─── Step 5: Generate frontend config ─────────────────────────
write-frontend-env:
	@echo "[5/8] Generating frontend config from stack outputs..."
	@API_URL=$$(aws cloudformation describe-stacks \
		--stack-name $(STACK_NAME) \
		--query "Stacks[0].Outputs[?OutputKey=='ApiGatewayUrl'].OutputValue" \
		--output text) && \
	POOL_ID=$$(aws cloudformation describe-stacks \
		--stack-name $(STACK_NAME) \
		--query "Stacks[0].Outputs[?OutputKey=='UserPoolId'].OutputValue" \
		--output text) && \
	CLIENT_ID=$$(aws cloudformation describe-stacks \
		--stack-name $(STACK_NAME) \
		--query "Stacks[0].Outputs[?OutputKey=='UserPoolClientId'].OutputValue" \
		--output text) && \
	IDENTITY_POOL_ID=$$(aws cloudformation describe-stacks \
		--stack-name $(STACK_NAME) \
		--query "Stacks[0].Outputs[?OutputKey=='VoiceIdentityPoolId'].OutputValue" \
		--output text) && \
	VOICE_RUNTIME_ARN="" && \
	VOICE_RUNTIME_ID=$$(aws ssm get-parameter \
		--name "/$(STACK_PREFIX)/voice/runtime-id" \
		--query "Parameter.Value" --output text 2>/dev/null) && \
	if [ "$$VOICE_RUNTIME_ID" != "None" ] && [ -n "$$VOICE_RUNTIME_ID" ]; then \
		VOICE_RUNTIME_ARN="arn:aws:bedrock-agentcore:$(REGION):$(ACCOUNT_ID):runtime/$$VOICE_RUNTIME_ID"; \
	fi && \
	CHAT_RUNTIME_ARN="" && \
	CHAT_RUNTIME_ID=$$(aws ssm get-parameter \
		--name "/$(STACK_PREFIX)/chat/runtime-id" \
		--query "Parameter.Value" --output text 2>/dev/null) && \
	if [ "$$CHAT_RUNTIME_ID" != "None" ] && [ -n "$$CHAT_RUNTIME_ID" ]; then \
		CHAT_RUNTIME_ARN="arn:aws:bedrock-agentcore:$(REGION):$(ACCOUNT_ID):runtime/$$CHAT_RUNTIME_ID"; \
	fi && \
	printf '%s\n' \
		"# Auto-generated by make deploy - do not edit manually" \
		"NEXT_PUBLIC_API_URL=$$API_URL" \
		"NEXT_PUBLIC_COGNITO_USER_POOL_ID=$$POOL_ID" \
		"NEXT_PUBLIC_COGNITO_CLIENT_ID=$$CLIENT_ID" \
		"NEXT_PUBLIC_COGNITO_REGION=$(REGION)" \
		"NEXT_PUBLIC_COGNITO_IDENTITY_POOL_ID=$$IDENTITY_POOL_ID" \
		"NEXT_PUBLIC_AWS_REGION=$(REGION)" \
		"NEXT_PUBLIC_AGENTCORE_RUNTIME_ARN=$$VOICE_RUNTIME_ARN" \
		"NEXT_PUBLIC_CHAT_RUNTIME_ARN=$$CHAT_RUNTIME_ARN" \
		> frontend/.env.production
	@echo "    done"

# ─── Step 6: Build frontend ───────────────────────────────────
build-frontend:
	@echo "[6/8] Building frontend..."
	@cd frontend && npm ci --legacy-peer-deps --silent 2>/dev/null && npm run build > /dev/null 2>&1
	@echo "    done"

# ─── Step 7: Deploy frontend ──────────────────────────────────
# LUMI is served from the /lumi/ prefix on the shared StayOS S3 bucket +
# CloudFront distribution (the StayOS shell owns the site root "/", PULSE owns
# /pulse/). Sync the static export into s3://<frontend>/lumi/. The --delete is
# scoped to the /lumi/ prefix, so it never touches the shell (root) or /pulse/.
deploy-frontend:
	@echo "[7/8] Deploying frontend to S3 (/lumi prefix)..."
	@aws s3 sync frontend/out/ s3://$(FRONTEND_BUCKET)/lumi/ --delete --quiet
	@echo "    done"

# ─── Step 8: Invalidate CDN ───────────────────────────────────
# Invalidate only LUMI's path prefix so a LUMI redeploy does not blow away the
# shell (root) or PULSE cache entries on the shared distribution.
invalidate-cdn:
	@echo "[8/8] Invalidating CDN cache (/lumi/*)..."
	@aws cloudfront create-invalidation \
		--distribution-id $$(aws cloudformation describe-stacks \
			--stack-name $(STACK_NAME) \
			--query "Stacks[0].Outputs[?OutputKey=='FrontendDistributionId'].OutputValue" \
			--output text) \
		--paths "/lumi/*" > /dev/null
	@echo "    done"

# ─── Testing ──────────────────────────────────────────────────
test: test-backend test-frontend
	@echo "All tests passed"

test-backend:
	@echo "Running backend tests..."
	@cd backend && python3 -m pytest tests/ -v

test-frontend:
	@echo "Running frontend tests..."
	@cd frontend && npm test

lint:
	@echo "Linting backend..."
	@cd backend && python3 -m flake8 functions/ --max-line-length 120
	@cd backend && python3 -m mypy functions/ --ignore-missing-imports
	@echo "Linting frontend..."
	@cd frontend && npm run lint

# ─── Generate AI Briefs ───────────────────────────────────────
# Triggers the orchestrator Lambda to generate today's brief for all GMs.
# Runs async (fire-and-forget) since it takes 2-3 min per property.
# On fresh deploy, the CFN seed provides synthetic briefs; this enriches
# them with real AI narratives + Polly audio + live VIP data.
generate-briefs:
	@echo "[9/9] Generating AI briefs for all properties (async)..."
	@aws lambda invoke \
		--function-name $(STACK_PREFIX)-orchestrator \
		--invocation-type Event \
		--cli-binary-format raw-in-base64-out \
		--payload '{"source":"scheduler","action":"generate-all"}' \
		--region $(REGION) \
		/tmp/orchestrator-async.json > /dev/null 2>&1 && \
	echo "    done (briefs will be ready in ~2-3 minutes)"

# ─── AgentCore Gateway Deploy ──────────────────────────────────
# Creates or updates the AgentCore Gateway that exposes the Tool
# Lambda's 5 read-only hotel operations tools as MCP-compatible
# tools. Auth is IAM-only (no bearer tokens) and MCP response
# streaming is enabled so tool progress is delivered via SSE.
# Gateway ID and endpoint URL are tracked in SSM (mirrors the
# voice-deploy state pattern). AgentCore Gateway has no CFN resource
# type yet, so it (and its dedicated IAM role) is managed via CLI.
#
# Usage:
#   make gateway-deploy   # create/update Gateway + register Lambda target

GATEWAY_NAME := $(STACK_PREFIX)-gateway
GATEWAY_TARGET_NAME := tools
GATEWAY_ROLE_NAME := $(STACK_PREFIX)-gateway-role-$(REGION)

gateway-deploy:
	@echo "  [gateway] Fetching Tool Lambda ARN and WAF WebACL ARN from stack outputs..."
	@TOOL_LAMBDA_ARN=$$(aws cloudformation describe-stacks \
		--stack-name $(STACK_NAME) \
		--query "Stacks[0].Outputs[?OutputKey=='ToolLambdaArn'].OutputValue" \
		--output text) && \
	WAF_WEB_ACL_ARN=$$(aws cloudformation describe-stacks \
		--stack-name $(STACK_NAME) \
		--query "Stacks[0].Outputs[?OutputKey=='GatewayWafWebAclArn'].OutputValue" \
		--output text) && \
	echo "  [gateway] Ensuring Gateway IAM role exists ($(GATEWAY_ROLE_NAME))..." && \
	if aws iam get-role --role-name $(GATEWAY_ROLE_NAME) > /dev/null 2>&1; then \
		echo "  [gateway] Role already exists"; \
	else \
		aws iam create-role \
			--role-name $(GATEWAY_ROLE_NAME) \
			--assume-role-policy-document '{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Principal":{"Service":"bedrock-agentcore.amazonaws.com"},"Action":"sts:AssumeRole"}]}' > /dev/null && \
		echo "  [gateway] Role created - waiting for IAM propagation..." && \
		sleep 10; \
	fi && \
	GATEWAY_ROLE_ARN=$$(aws iam get-role --role-name $(GATEWAY_ROLE_NAME) --query 'Role.Arn' --output text) && \
	aws iam put-role-policy \
		--role-name $(GATEWAY_ROLE_NAME) \
		--policy-name InvokeToolLambda \
		--policy-document "{\"Version\":\"2012-10-17\",\"Statement\":[{\"Effect\":\"Allow\",\"Action\":\"lambda:InvokeFunction\",\"Resource\":\"$$TOOL_LAMBDA_ARN\"}]}" > /dev/null && \
	echo "  [gateway] Checking for existing Gateway..." && \
	if GATEWAY_ID=$$(aws ssm get-parameter \
		--name "/$(STACK_PREFIX)/gateway/gateway-id" \
		--query "Parameter.Value" --output text 2>/dev/null) && \
	   [ "$$GATEWAY_ID" != "None" ] && [ -n "$$GATEWAY_ID" ]; then \
		echo "  [gateway] Updating existing Gateway: $$GATEWAY_ID" && \
		aws bedrock-agentcore-control update-gateway \
			--gateway-identifier "$$GATEWAY_ID" \
			--name "$(GATEWAY_NAME)" \
			--role-arn "$$GATEWAY_ROLE_ARN" \
			--protocol-type MCP \
			--protocol-configuration '{"mcp":{"streamingConfiguration":{"enableResponseStreaming":true}}}' \
			--authorizer-type AWS_IAM \
			--exception-level DEBUG > /dev/null ; \
	else \
		echo "  [gateway] Creating new Gateway..." && \
		GATEWAY_ID=$$(aws bedrock-agentcore-control create-gateway \
			--name "$(GATEWAY_NAME)" \
			--description "StayOS AgentCore Gateway - MCP tool endpoint for hotel operations data" \
			--role-arn "$$GATEWAY_ROLE_ARN" \
			--protocol-type MCP \
			--protocol-configuration '{"mcp":{"streamingConfiguration":{"enableResponseStreaming":true}}}' \
			--authorizer-type AWS_IAM \
			--exception-level DEBUG \
			--query 'gatewayId' --output text) && \
		aws ssm put-parameter \
			--name "/$(STACK_PREFIX)/gateway/gateway-id" \
			--value "$$GATEWAY_ID" \
			--type String \
			--overwrite > /dev/null && \
		echo "  [gateway] Gateway created: $$GATEWAY_ID" && \
		echo "  [gateway] Stored in SSM: /$(STACK_PREFIX)/gateway/gateway-id" ; \
	fi && \
	GATEWAY_ID=$$(aws ssm get-parameter \
		--name "/$(STACK_PREFIX)/gateway/gateway-id" \
		--query "Parameter.Value" --output text) && \
	echo "  [gateway] Waiting for Gateway READY status..." && \
	while true; do \
		STATUS=$$(aws bedrock-agentcore-control get-gateway \
			--gateway-identifier "$$GATEWAY_ID" \
			--query 'status' --output text); \
		if [ "$$STATUS" = "READY" ]; then \
			echo "  [gateway] Gateway is READY"; \
			break; \
		elif [ "$$STATUS" = "FAILED" ] || [ "$$STATUS" = "UPDATE_UNSUCCESSFUL" ]; then \
			echo "" && \
			echo "  ERROR: AgentCore Gateway entered $$STATUS state." && \
			echo "" && \
			exit 1; \
		else \
			sleep 10; \
		fi; \
	done && \
	GATEWAY_URL=$$(aws bedrock-agentcore-control get-gateway \
		--gateway-identifier "$$GATEWAY_ID" --query 'gatewayUrl' --output text) && \
	GATEWAY_ARN=$$(aws bedrock-agentcore-control get-gateway \
		--gateway-identifier "$$GATEWAY_ID" --query 'gatewayArn' --output text) && \
	aws ssm put-parameter \
		--name "/$(STACK_PREFIX)/gateway/endpoint-url" \
		--value "$$GATEWAY_URL" \
		--type String \
		--overwrite > /dev/null && \
	echo "  [gateway] Endpoint URL stored in SSM: /$(STACK_PREFIX)/gateway/endpoint-url" && \
	echo "  [gateway] Reading tool schema and registering Gateway Target..." && \
	TARGET_CONFIG=$$(python3 -c "import json, sys; tools = json.load(open('backend/tools/tool-schema.json'))['tools']; print(json.dumps({'mcp': {'lambda': {'lambdaArn': sys.argv[1], 'toolSchema': {'inlinePayload': tools}}}}))" "$$TOOL_LAMBDA_ARN") && \
	TARGET_ID=$$(aws bedrock-agentcore-control list-gateway-targets \
		--gateway-identifier "$$GATEWAY_ID" \
		--query "items[?name=='$(GATEWAY_TARGET_NAME)'].targetId | [0]" --output text) && \
	if [ "$$TARGET_ID" != "None" ] && [ -n "$$TARGET_ID" ]; then \
		echo "  [gateway] Updating existing Gateway Target: $$TARGET_ID" && \
		aws bedrock-agentcore-control update-gateway-target \
			--gateway-identifier "$$GATEWAY_ID" \
			--target-id "$$TARGET_ID" \
			--name "$(GATEWAY_TARGET_NAME)" \
			--target-configuration "$$TARGET_CONFIG" \
			--credential-provider-configurations '[{"credentialProviderType":"GATEWAY_IAM_ROLE"}]' > /dev/null ; \
	else \
		echo "  [gateway] Registering Tool Lambda as Gateway Target..." && \
		TARGET_ID=$$(aws bedrock-agentcore-control create-gateway-target \
			--gateway-identifier "$$GATEWAY_ID" \
			--name "$(GATEWAY_TARGET_NAME)" \
			--description "LUMI read-only hotel operations tools (Tool Lambda)" \
			--target-configuration "$$TARGET_CONFIG" \
			--credential-provider-configurations '[{"credentialProviderType":"GATEWAY_IAM_ROLE"}]' \
			--query 'targetId' --output text) && \
		echo "  [gateway] Target created: $$TARGET_ID" ; \
	fi && \
	echo "  [gateway] Waiting for Gateway Target READY status..." && \
	while true; do \
		TSTATUS=$$(aws bedrock-agentcore-control get-gateway-target \
			--gateway-identifier "$$GATEWAY_ID" \
			--target-id "$$TARGET_ID" \
			--query 'status' --output text); \
		if [ "$$TSTATUS" = "READY" ]; then \
			echo "  [gateway] Gateway Target is READY"; \
			break; \
		elif [ "$$TSTATUS" = "FAILED" ] || [ "$$TSTATUS" = "UPDATE_UNSUCCESSFUL" ] || [ "$$TSTATUS" = "SYNCHRONIZE_UNSUCCESSFUL" ]; then \
			echo "" && \
			echo "  ERROR: Gateway Target entered $$TSTATUS state." && \
			echo "" && \
			exit 1; \
		else \
			sleep 10; \
		fi; \
	done && \
	echo "  [gateway] Associating WAF WebACL with Gateway..." && \
	if aws wafv2 associate-web-acl \
		--web-acl-arn "$$WAF_WEB_ACL_ARN" \
		--resource-arn "$$GATEWAY_ARN" > /dev/null 2>&1; then \
		echo "  [gateway] WAF WebACL associated"; \
	else \
		echo ""; \
		echo "  WARNING: Could not associate WAF WebACL with the Gateway (commonly"; \
		echo "  WAFUnavailableEntityException). This has been observed as an AWS-side gap in the"; \
		echo "  WAF <-> AgentCore Gateway integration rather than a config issue on our end - it is"; \
		echo "  not fixed by waiting/retrying immediately. Continuing without failing the deploy:"; \
		echo "  per AWS docs, a Gateway with no web ACL associated has zero WAF overhead and simply"; \
		echo "  runs without that extra protection layer in the meantime."; \
		echo ""; \
		echo "  Retry manually once resolved with:"; \
		echo "    aws wafv2 associate-web-acl --web-acl-arn \"$$WAF_WEB_ACL_ARN\" --resource-arn \"$$GATEWAY_ARN\""; \
		echo ""; \
	fi && \
	echo "  [gateway] Gateway ID:  $$GATEWAY_ID" && \
	echo "  [gateway] Gateway URL: $$GATEWAY_URL"

# ─── AgentCore Gateway Destroy ─────────────────────────────────
# Disassociates the WAF WebACL, deletes all Gateway Targets, deletes
# the Gateway itself, and removes the SSM parameters. The Gateway
# IAM role (CLI-managed) is left in place so a subsequent
# gateway-deploy can reuse it without recreating permissions.
#
# Usage:
#   make gateway-destroy   # tear down the AgentCore Gateway only

gateway-destroy:
	@GATEWAY_ID=$$(aws ssm get-parameter \
		--name "/$(STACK_PREFIX)/gateway/gateway-id" \
		--query "Parameter.Value" --output text 2>/dev/null); \
	if [ "$$GATEWAY_ID" != "None" ] && [ -n "$$GATEWAY_ID" ]; then \
		GATEWAY_ARN=$$(aws bedrock-agentcore-control get-gateway \
			--gateway-identifier "$$GATEWAY_ID" \
			--query 'gatewayArn' --output text 2>/dev/null); \
		if [ -n "$$GATEWAY_ARN" ] && [ "$$GATEWAY_ARN" != "None" ]; then \
			echo "  [gateway] Disassociating WAF WebACL from Gateway..." && \
			aws wafv2 disassociate-web-acl --resource-arn "$$GATEWAY_ARN" > /dev/null 2>&1 || true; \
		fi; \
		echo "  [gateway] Deleting Gateway Targets..." && \
		for TARGET_ID in $$(aws bedrock-agentcore-control list-gateway-targets \
			--gateway-identifier "$$GATEWAY_ID" --query 'items[].targetId' --output text 2>/dev/null); do \
			aws bedrock-agentcore-control delete-gateway-target \
				--gateway-identifier "$$GATEWAY_ID" --target-id "$$TARGET_ID" > /dev/null 2>&1 || true; \
		done && \
		echo "  [gateway] Deleting Gateway: $$GATEWAY_ID" && \
		aws bedrock-agentcore-control delete-gateway --gateway-identifier "$$GATEWAY_ID" && \
		aws ssm delete-parameter --name "/$(STACK_PREFIX)/gateway/gateway-id" > /dev/null 2>&1 || true; \
		aws ssm delete-parameter --name "/$(STACK_PREFIX)/gateway/endpoint-url" > /dev/null 2>&1 || true; \
		echo "  [gateway] Gateway deleted and SSM parameters removed"; \
	else \
		echo "  [gateway] No Gateway ID found in SSM - nothing to delete"; \
	fi

# ─── Voice Agent Build (CodeBuild) ────────────────────────────
# Packages voice agent source, uploads to S3, triggers CodeBuild
# for ARM64 container build, and waits for completion.
# CodeBuild pushes to ECR with :latest + timestamped tag.
#
# Usage:
#   make voice-build    # trigger remote ARM64 container build

VOICE_BUILD_PROJECT := $(STACK_PREFIX)-voice-agent-build
VOICE_ECR_URI := $(ACCOUNT_ID).dkr.ecr.$(REGION).amazonaws.com/$(STACK_PREFIX)-voice-agent

voice-build:
	@echo "  [voice] Packaging voice agent source..."
	@mkdir -p build
	@cd backend/services/voice-agent && zip -r ../../../build/voice-agent-source.zip . \
		-x "tests/*" "__pycache__/*" "*.pyc" "agentcore/*" ".pytest_cache/*" > /dev/null
	@echo "  [voice] Uploading source to S3..."
	@aws s3 cp build/voice-agent-source.zip \
		s3://$(DEPLOY_BUCKET)/voice-agent-source/voice-agent-source.zip --quiet
	@echo "  [voice] Starting CodeBuild (ARM64 container build)..."
	@BUILD_ID=$$(aws codebuild start-build \
		--project-name $(VOICE_BUILD_PROJECT) \
		--query 'build.id' --output text) && \
	echo "  [voice] Build started: $$BUILD_ID" && \
	echo "  [voice] Waiting for build to complete..." && \
	while true; do \
		STATUS=$$(aws codebuild batch-get-builds --ids $$BUILD_ID \
			--query 'builds[0].buildStatus' --output text); \
		if [ "$$STATUS" = "SUCCEEDED" ]; then \
			echo "  [voice] Build succeeded"; \
			echo "  [voice] Image: $(VOICE_ECR_URI):latest"; \
			break; \
		elif [ "$$STATUS" = "IN_PROGRESS" ]; then \
			sleep 10; \
		else \
			LOG_URL=$$(aws codebuild batch-get-builds --ids $$BUILD_ID \
				--query 'builds[0].logs.deepLink' --output text); \
			echo ""; \
			echo "  CodeBuild failed with status: $$STATUS"; \
			echo ""; \
			echo "  View build logs: $$LOG_URL"; \
			echo ""; \
			exit 1; \
		fi; \
	done

# ─── Voice Agent Deploy (AgentCore Runtime) ───────────────────
# Creates or updates the Bedrock AgentCore Runtime for the voice agent.
# First deploy creates the runtime; subsequent deploys update the container URI.
# State is tracked in .voice-runtime-id (gitignored).
#
# Usage:
#   make voice-deploy   # build + deploy to AgentCore

voice-deploy: voice-build
	@echo "  [voice] Deploying to AgentCore Runtime..."
	@ROLE_ARN=$$(aws cloudformation describe-stacks \
		--stack-name $(STACK_NAME) \
		--query "Stacks[0].Outputs[?OutputKey=='VoiceAgentCoreRoleArn'].OutputValue" \
		--output text) && \
	SETTINGS_TABLE="$(STACK_PREFIX)-settings" && \
	USER_POOL_ID=$$(aws cloudformation describe-stacks \
		--stack-name $(STACK_NAME) \
		--query "Stacks[0].Outputs[?OutputKey=='UserPoolId'].OutputValue" \
		--output text) && \
	if RUNTIME_ID=$$(aws ssm get-parameter \
		--name "/$(STACK_PREFIX)/voice/runtime-id" \
		--query "Parameter.Value" --output text 2>/dev/null) && \
	   [ "$$RUNTIME_ID" != "None" ] && [ -n "$$RUNTIME_ID" ]; then \
		echo "  [voice] Updating existing runtime: $$RUNTIME_ID" && \
		aws bedrock-agentcore-control update-agent-runtime \
			--agent-runtime-id "$$RUNTIME_ID" \
			--role-arn "$$ROLE_ARN" \
			--network-configuration '{"networkMode":"PUBLIC"}' \
			--agent-runtime-artifact "{\"containerConfiguration\":{\"containerUri\":\"$(VOICE_ECR_URI):latest\"}}" \
			--environment-variables "{\"SETTINGS_TABLE_NAME\":\"$$SETTINGS_TABLE\",\"RESERVATIONS_TABLE_NAME\":\"$(STACK_PREFIX)-reservations\",\"ROOMS_TABLE_NAME\":\"$(STACK_PREFIX)-rooms\",\"GUESTS_TABLE_NAME\":\"$(STACK_PREFIX)-guests\",\"REVENUES_TABLE_NAME\":\"$(STACK_PREFIX)-revenues\",\"WORK_ORDERS_TABLE_NAME\":\"$(STACK_PREFIX)-work-orders\",\"BRIEFS_TABLE_NAME\":\"$(STACK_PREFIX)-briefs\",\"COGNITO_USER_POOL_ID\":\"$$USER_POOL_ID\",\"AWS_DEFAULT_REGION\":\"$(REGION)\",\"UNIFIED_TRACES_DESTINATION_ENABLED\":\"true\"}" ; \
	else \
		echo "  [voice] Creating new AgentCore Runtime..." && \
		RUNTIME_ID=$$(aws bedrock-agentcore-control create-agent-runtime \
			--agent-runtime-name "$(STACK_PREFIX)_voice_agent" \
			--description "LUMI Voice Agent - Nova Sonic bidirectional streaming" \
			--role-arn "$$ROLE_ARN" \
			--network-configuration '{"networkMode":"PUBLIC"}' \
			--agent-runtime-artifact "{\"containerConfiguration\":{\"containerUri\":\"$(VOICE_ECR_URI):latest\"}}" \
			--environment-variables "{\"SETTINGS_TABLE_NAME\":\"$$SETTINGS_TABLE\",\"RESERVATIONS_TABLE_NAME\":\"$(STACK_PREFIX)-reservations\",\"ROOMS_TABLE_NAME\":\"$(STACK_PREFIX)-rooms\",\"GUESTS_TABLE_NAME\":\"$(STACK_PREFIX)-guests\",\"REVENUES_TABLE_NAME\":\"$(STACK_PREFIX)-revenues\",\"WORK_ORDERS_TABLE_NAME\":\"$(STACK_PREFIX)-work-orders\",\"BRIEFS_TABLE_NAME\":\"$(STACK_PREFIX)-briefs\",\"COGNITO_USER_POOL_ID\":\"$$USER_POOL_ID\",\"AWS_DEFAULT_REGION\":\"$(REGION)\",\"UNIFIED_TRACES_DESTINATION_ENABLED\":\"true\"}" \
			--query 'agentRuntimeId' --output text) && \
		aws ssm put-parameter \
			--name "/$(STACK_PREFIX)/voice/runtime-id" \
			--value "$$RUNTIME_ID" \
			--type String \
			--overwrite > /dev/null && \
		echo "  [voice] Runtime created: $$RUNTIME_ID" && \
		echo "  [voice] Stored in SSM: /$(STACK_PREFIX)/voice/runtime-id" ; \
	fi && \
	RUNTIME_ID=$$(aws ssm get-parameter \
		--name "/$(STACK_PREFIX)/voice/runtime-id" \
		--query "Parameter.Value" --output text) && \
	echo "  [voice] Waiting for runtime READY status..." && \
	while true; do \
		STATUS=$$(aws bedrock-agentcore-control get-agent-runtime \
			--agent-runtime-id "$$RUNTIME_ID" \
			--query 'status' --output text); \
		if [ "$$STATUS" = "READY" ]; then \
			echo "  [voice] Runtime is READY"; \
			echo "  [voice] Runtime ID: $$RUNTIME_ID"; \
			break; \
		elif [ "$$STATUS" = "FAILED" ]; then \
			echo ""; \
			echo "  ERROR: AgentCore Runtime entered FAILED state."; \
			echo ""; \
			echo "  Check CloudWatch logs: /$(STACK_PREFIX)/agentcore/voice-agent"; \
			echo ""; \
			exit 1; \
		else \
			sleep 10; \
		fi; \
	done

# ─── Voice Agent Destroy (AgentCore Runtime) ──────────────────
# Deletes the AgentCore Runtime and removes local state file.
# CloudFormation handles ECR + CodeBuild resource deletion separately.
#
# Usage:
#   make voice-destroy   # tear down AgentCore Runtime only

voice-destroy:
	@RUNTIME_ID=$$(aws ssm get-parameter \
		--name "/$(STACK_PREFIX)/voice/runtime-id" \
		--query "Parameter.Value" --output text 2>/dev/null); \
	if [ "$$RUNTIME_ID" != "None" ] && [ -n "$$RUNTIME_ID" ]; then \
		echo "  [voice] Deleting AgentCore Runtime: $$RUNTIME_ID" && \
		aws bedrock-agentcore-control delete-agent-runtime \
			--agent-runtime-id "$$RUNTIME_ID" && \
		aws ssm delete-parameter \
			--name "/$(STACK_PREFIX)/voice/runtime-id" > /dev/null && \
		echo "  [voice] Runtime deleted and SSM parameter removed"; \
	else \
		echo "  [voice] No runtime ID found in SSM - nothing to delete"; \
	fi

# ─── Chat Agent Build (CodeBuild) ─────────────────────────────
# Packages chat agent source, uploads to S3, triggers CodeBuild
# for ARM64 container build, and waits for completion.
# CodeBuild pushes to ECR with :latest + timestamped tag.
#
# Usage:
#   make chat-build    # trigger remote ARM64 container build

CHAT_BUILD_PROJECT := $(STACK_PREFIX)-chat-agent-build
CHAT_ECR_URI := $(ACCOUNT_ID).dkr.ecr.$(REGION).amazonaws.com/$(STACK_PREFIX)-chat-agent

chat-build:
	@echo "  [chat] Packaging chat agent source..."
	@mkdir -p build
	@cd backend/services/chat-agent && zip -r ../../../build/chat-agent-source.zip . \
		-x "tests/*" "__pycache__/*" "*.pyc" "agentcore/*" ".pytest_cache/*" > /dev/null
	@echo "  [chat] Uploading source to S3..."
	@aws s3 cp build/chat-agent-source.zip \
		s3://$(DEPLOY_BUCKET)/chat-agent-source/chat-agent-source.zip --quiet
	@echo "  [chat] Starting CodeBuild (ARM64 container build)..."
	@BUILD_ID=$$(aws codebuild start-build \
		--project-name $(CHAT_BUILD_PROJECT) \
		--query 'build.id' --output text) && \
	echo "  [chat] Build started: $$BUILD_ID" && \
	echo "  [chat] Waiting for build to complete..." && \
	while true; do \
		STATUS=$$(aws codebuild batch-get-builds --ids $$BUILD_ID \
			--query 'builds[0].buildStatus' --output text); \
		if [ "$$STATUS" = "SUCCEEDED" ]; then \
			echo "  [chat] Build succeeded"; \
			echo "  [chat] Image: $(CHAT_ECR_URI):latest"; \
			break; \
		elif [ "$$STATUS" = "IN_PROGRESS" ]; then \
			sleep 10; \
		else \
			LOG_URL=$$(aws codebuild batch-get-builds --ids $$BUILD_ID \
				--query 'builds[0].logs.deepLink' --output text); \
			echo ""; \
			echo "  CodeBuild failed with status: $$STATUS"; \
			echo ""; \
			echo "  View build logs: $$LOG_URL"; \
			echo ""; \
			exit 1; \
		fi; \
	done

# ─── Chat Agent Deploy (AgentCore Runtime) ────────────────────
# Creates or updates the Bedrock AgentCore Runtime for the chat agent.
# First deploy creates the runtime; subsequent deploys update the container URI.
# State is tracked in SSM at /${StackPrefix}/chat/runtime-id.
#
# Usage:
#   make chat-deploy   # build + deploy to AgentCore

chat-deploy: chat-build
	@echo "  [chat] Deploying to AgentCore Runtime..."
	@ROLE_ARN=$$(aws cloudformation describe-stacks \
		--stack-name $(STACK_NAME) \
		--query "Stacks[0].Outputs[?OutputKey=='ChatAgentCoreRoleArn'].OutputValue" \
		--output text) && \
	GATEWAY_ENDPOINT_URL=$$(aws ssm get-parameter \
		--name "/$(STACK_PREFIX)/gateway/endpoint-url" \
		--query "Parameter.Value" --output text) && \
	USER_POOL_ID=$$(aws cloudformation describe-stacks \
		--stack-name $(STACK_NAME) \
		--query "Stacks[0].Outputs[?OutputKey=='UserPoolId'].OutputValue" \
		--output text) && \
	if RUNTIME_ID=$$(aws ssm get-parameter \
		--name "/$(STACK_PREFIX)/chat/runtime-id" \
		--query "Parameter.Value" --output text 2>/dev/null) && \
	   [ "$$RUNTIME_ID" != "None" ] && [ -n "$$RUNTIME_ID" ]; then \
		echo "  [chat] Updating existing runtime: $$RUNTIME_ID" && \
		aws bedrock-agentcore-control update-agent-runtime \
			--agent-runtime-id "$$RUNTIME_ID" \
			--role-arn "$$ROLE_ARN" \
			--network-configuration '{"networkMode":"PUBLIC"}' \
			--agent-runtime-artifact "{\"containerConfiguration\":{\"containerUri\":\"$(CHAT_ECR_URI):latest\"}}" \
			--environment-variables "{\"GATEWAY_ENDPOINT_URL\":\"$$GATEWAY_ENDPOINT_URL\",\"COGNITO_USER_POOL_ID\":\"$$USER_POOL_ID\",\"AWS_DEFAULT_REGION\":\"$(REGION)\"}" ; \
	else \
		echo "  [chat] Creating new AgentCore Runtime..." && \
		RUNTIME_ID=$$(aws bedrock-agentcore-control create-agent-runtime \
			--agent-runtime-name "$(STACK_PREFIX)_chat_agent" \
			--description "LUMI Chat Agent - text-based conversational agent via AgentCore Gateway" \
			--role-arn "$$ROLE_ARN" \
			--network-configuration '{"networkMode":"PUBLIC"}' \
			--agent-runtime-artifact "{\"containerConfiguration\":{\"containerUri\":\"$(CHAT_ECR_URI):latest\"}}" \
			--environment-variables "{\"GATEWAY_ENDPOINT_URL\":\"$$GATEWAY_ENDPOINT_URL\",\"COGNITO_USER_POOL_ID\":\"$$USER_POOL_ID\",\"AWS_DEFAULT_REGION\":\"$(REGION)\"}" \
			--query 'agentRuntimeId' --output text) && \
		aws ssm put-parameter \
			--name "/$(STACK_PREFIX)/chat/runtime-id" \
			--value "$$RUNTIME_ID" \
			--type String \
			--overwrite > /dev/null && \
		echo "  [chat] Runtime created: $$RUNTIME_ID" && \
		echo "  [chat] Stored in SSM: /$(STACK_PREFIX)/chat/runtime-id" ; \
	fi && \
	RUNTIME_ID=$$(aws ssm get-parameter \
		--name "/$(STACK_PREFIX)/chat/runtime-id" \
		--query "Parameter.Value" --output text) && \
	echo "  [chat] Waiting for runtime READY status..." && \
	while true; do \
		STATUS=$$(aws bedrock-agentcore-control get-agent-runtime \
			--agent-runtime-id "$$RUNTIME_ID" \
			--query 'status' --output text); \
		if [ "$$STATUS" = "READY" ]; then \
			echo "  [chat] Runtime is READY"; \
			echo "  [chat] Runtime ID: $$RUNTIME_ID"; \
			break; \
		elif [ "$$STATUS" = "FAILED" ]; then \
			echo ""; \
			echo "  ERROR: AgentCore Runtime entered FAILED state."; \
			echo ""; \
			echo "  Check CloudWatch logs: /$(STACK_PREFIX)/agentcore/chat-agent"; \
			echo ""; \
			exit 1; \
		else \
			sleep 10; \
		fi; \
	done

# ─── Chat Agent Destroy (AgentCore Runtime) ───────────────────
# Deletes the AgentCore Runtime and removes the SSM parameter.
# CloudFormation handles ECR + CodeBuild resource deletion separately.
#
# Usage:
#   make chat-destroy   # tear down AgentCore Runtime only

chat-destroy:
	@RUNTIME_ID=$$(aws ssm get-parameter \
		--name "/$(STACK_PREFIX)/chat/runtime-id" \
		--query "Parameter.Value" --output text 2>/dev/null); \
	if [ "$$RUNTIME_ID" != "None" ] && [ -n "$$RUNTIME_ID" ]; then \
		echo "  [chat] Deleting AgentCore Runtime: $$RUNTIME_ID" && \
		aws bedrock-agentcore-control delete-agent-runtime \
			--agent-runtime-id "$$RUNTIME_ID" && \
		aws ssm delete-parameter \
			--name "/$(STACK_PREFIX)/chat/runtime-id" > /dev/null && \
		echo "  [chat] Runtime deleted and SSM parameter removed"; \
	else \
		echo "  [chat] No runtime ID found in SSM - nothing to delete"; \
	fi

# ─── Re-seed Data ─────────────────────────────────────────────
# Clears all dataset tables and regenerates 30 days of fresh mock data.
# Safe to run anytime — existing stale data is replaced.
reseed:
	@echo ""
	@echo "╔══════════════════════════════════════════════╗"
	@echo "║         Re-seeding StayOS mock data         ║"
	@echo "╚══════════════════════════════════════════════╝"
	@echo ""
	@echo "  [1/3] Invoking seed-data Lambda (Force mode)..."
	@echo "        This clears all 5 dataset tables and regenerates 30 days"
	@echo "        of hotel operations data (~24,500 items across 5 properties)."
	@echo ""
	@echo "        Tables being cleared:"
	@echo "          • lumi-reservations"
	@echo "          • lumi-rooms"
	@echo "          • lumi-guests"
	@echo "          • lumi-revenues"
	@echo "          • lumi-work-orders"
	@echo ""
	@echo "        Invoking Lambda: $(STACK_PREFIX)-seed-data..."
	@aws lambda invoke \
		--function-name $(STACK_PREFIX)-seed-data \
		--cli-binary-format raw-in-base64-out \
		--payload '{"RequestType":"Create","ResourceProperties":{},"Force":true}' \
		--region $(REGION) \
		/tmp/reseed-response.json > /tmp/reseed-invoke.json
	@STATUS=$$(python3 -c "import json; r=json.load(open('/tmp/reseed-invoke.json')); print(r.get('FunctionError','SUCCESS'))"); \
	if [ "$$STATUS" = "SUCCESS" ]; then \
		echo "  ✅ Seed data regenerated successfully"; \
		echo ""; \
		echo "  [2/3] Generating AI briefs for all GMs..."; \
		echo "        Invoking Lambda: $(STACK_PREFIX)-orchestrator"; \
		echo "        Payload: {action: generate-all}"; \
		echo "        This generates Bedrock narratives + Polly audio for each GM."; \
		echo "        (async — runs in background, takes ~2-3 min per property)"; \
		echo ""; \
		aws lambda invoke \
			--function-name $(STACK_PREFIX)-orchestrator \
			--invocation-type Event \
			--cli-binary-format raw-in-base64-out \
			--payload '{"source":"scheduler","action":"generate-all"}' \
			--region $(REGION) \
			/tmp/orchestrator-response.json > /dev/null 2>&1; \
		echo "  ✅ Orchestrator invoked (async — briefs ready in ~2-3 min)"; \
		echo ""; \
		echo "  [3/3] Summary"; \
		echo ""; \
		echo "        Tables refreshed:"; \
		echo "          • lumi-rooms          (~1,840 items)"; \
		echo "          • lumi-guests         (~250 items)"; \
		echo "          • lumi-revenues       (~150 items)"; \
		echo "          • lumi-reservations   (~21,500 items)"; \
		echo "          • lumi-work-orders    (~750 items)"; \
		echo ""; \
		echo "        Coverage: today-29 through today+1 (30 days)"; \
		echo "        Briefs:  generating async for 5 properties"; \
		echo ""; \
		echo "  ✅ Done — reload the dashboard in 2-3 minutes for fresh briefs."; \
	else \
		echo "  ❌ Seed failed: $$STATUS"; \
		echo ""; \
		echo "  Lambda response:"; \
		cat /tmp/reseed-response.json; \
	fi
	@echo ""

# ─── Cleanup ──────────────────────────────────────────────────
clean:
	@rm -rf build/ frontend/out/ frontend/.next/ backend/layers/dependencies/python/
	@echo "Clean"
