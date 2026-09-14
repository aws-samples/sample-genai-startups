.PHONY: help deploy invoke destroy clean \
        lambda-role lambdas project aws-targets \
        deploy-gateway gateway-targets tool deploy-final

# AgentCore Harness is in preview; default region.
export AWS_REGION ?= us-east-1

# AgentCore auto-names the harness after the project when scaffolded via
# `agentcore create --model-provider ...`. The full harness name is
# "<PROJECT_NAME>_<PROJECT_NAME>" under the hood and must be ≤ 40 chars,
# so we keep PROJECT_NAME intentionally short.
PROJECT_NAME  := PvtAviation
HARNESS_NAME  := $(PROJECT_NAME)
GATEWAY_NAME  := aviation-tools
MODEL_ID      := global.anthropic.claude-sonnet-4-6

PROJECT_DIR   := project
PROJECT_PATH  := $(PROJECT_DIR)/$(PROJECT_NAME)
PY            ?= python3
SCRIPTS_DIR   := scripts
CONFIG_DIR    := config
LAMBDA_PREFIX := PrivateAviationHarness

# Resolve caller identity for the aws-targets.json file the CLI expects.
ACCOUNT_ID    := $(shell aws sts get-caller-identity --query Account --output text 2>/dev/null)

REPO_ROOT     := $(shell pwd)
STATE_FILE    := $(REPO_ROOT)/$(CONFIG_DIR)/state.json
GET_LAMBDA    := $(PY) -c 'import json,sys; print(json.load(open("$(STATE_FILE)"))["lambda_arns"][sys.argv[1]])'

help:
	@echo "Targets:"
	@echo "  make deploy             — Full chain: IAM, Lambdas, scaffold, Gateway, targets, Harness"
	@echo "  make invoke             — Invoke the Harness with the demo booking prompt"
	@echo "  make destroy            — Delete Lambdas (Harness/Gateway teardown is manual — see README)"
	@echo "  make clean              — Remove local state.json and generated project files"
	@echo ""
	@echo "Region:  $(AWS_REGION)"
	@echo "Account: $(ACCOUNT_ID)"

# ── Deploy chain ────────────────────────────────────────────────────────────

# Two-phase deploy:
#   Phase A: Lambdas + project scaffold + first agentcore deploy
#            (creates Gateway and Harness resources in AWS)
#   Phase B: Add Lambda gateway-targets (which require the deployed Gateway)
#            + tool wiring + second agentcore deploy (syncs targets/tools)
deploy: lambda-role lambdas project aws-targets deploy-gateway gateway-targets tool deploy-final
	@echo ""
	@echo "Deploy complete. Run 'make invoke' to test."

# 1. Lambda execution role (boto3 — outside AgentCore CLI's concern)
lambda-role:
	cd $(SCRIPTS_DIR) && $(PY) setup_iam.py

# 2. Lambdas themselves (boto3 — CLI does not provision the tool backends)
lambdas:
	cd $(SCRIPTS_DIR) && $(PY) deploy_lambdas.py

# 3. Scaffold the AgentCore project and pre-declare a Gateway. The
#    --model-provider + --model-id flags on `agentcore create` route to
#    the harness path rather than the agent/runtime path.
project:
	@if [ ! -d "$(PROJECT_PATH)" ]; then \
	  agentcore create \
	    --name $(PROJECT_NAME) \
	    --model-provider bedrock \
	    --model-id $(MODEL_ID) \
	    --defaults \
	    --output-dir $(PROJECT_DIR) \
	    --skip-git --skip-python-setup --skip-install ; \
	  ( cd $(PROJECT_PATH) && agentcore add gateway \
	      --name $(GATEWAY_NAME) \
	      --description "Exposes private-aviation Lambdas as MCP tools" \
	      --authorizer-type NONE \
	      --no-semantic-search ) ; \
	else \
	  echo "Project directory $(PROJECT_PATH)/ already exists — skipping scaffold."; \
	fi

# 4. Populate aws-targets.json so `agentcore deploy` knows where to go,
#    and install the CDK project's npm dependencies.
aws-targets:
	@if [ -z "$(ACCOUNT_ID)" ]; then echo "Could not resolve AWS account ID"; exit 1; fi
	@printf '[\n  {\n    "name": "default",\n    "account": "$(ACCOUNT_ID)",\n    "region": "$(AWS_REGION)"\n  }\n]\n' > $(PROJECT_PATH)/agentcore/aws-targets.json
	@echo "Wrote $(PROJECT_PATH)/agentcore/aws-targets.json"
	@( cd $(PROJECT_PATH)/agentcore/cdk && npm install --silent )

# 5. First deploy — creates Gateway, Harness, and IAM roles.
deploy-gateway:
	cd $(PROJECT_PATH) && agentcore deploy --yes

# 6. Register each Lambda as a Gateway target (requires deployed Gateway).
#    Gateway target names must match ^([0-9a-zA-Z][-]?){1,100}$ — alnum + hyphens.
gateway-targets:
	@cd $(PROJECT_PATH) && \
	  for pair in get_owner_info:get-owner-info get_passengers:get-passengers book_reservation:book-reservation ; do \
	    lambda_key=$${pair%:*} ; \
	    target_name=$${pair#*:} ; \
	    agentcore add gateway-target \
	      --gateway $(GATEWAY_NAME) \
	      --name $$target_name \
	      --type lambda-function-arn \
	      --lambda-arn $$($(GET_LAMBDA) $$lambda_key) \
	      --tool-schema-file $(REPO_ROOT)/$(CONFIG_DIR)/tool_schemas/$$lambda_key.json ; \
	  done

# 7. Attach the Gateway to the Harness as a tool.
tool:
	cd $(PROJECT_PATH) && agentcore add tool \
	  --harness $(HARNESS_NAME) \
	  --name aviation-tools \
	  --type agentcore_gateway \
	  --gateway $(GATEWAY_NAME)

# 8. Final deploy — syncs gateway targets and harness tool wiring.
deploy-final:
	cd $(PROJECT_PATH) && agentcore deploy --yes

# ── Invoke ──────────────────────────────────────────────────────────────────

# Harness does not (yet) expose a built-in current-time tool the way Strands
# does for Runtime. The per-call --system-prompt override injects the
# current UTC time as a fact the agent can reference — demonstrating the
# "defaults at create, overrides at invocation" pattern along the way.
NOW := $(shell date -u +"%Y-%m-%dT%H:%M:%SZ")

invoke:
	cd $(PROJECT_PATH) && agentcore invoke \
	  --harness $(HARNESS_NAME) \
	  --system-prompt "Current time: $(NOW). Use this as the reference for any relative time expressions. You are an AI assistant for a private aviation company helping book private jet reservations. Disney World is near Orlando; the nearest airport is KMCO. Use ICAO airport codes. Format dates in ISO 8601." \
	  "Mr. John Doe (OwnerId: 9612f6c4-b7ff-4d82-b113-7b605e188ed9) is planning for a surprise trip to Disney World in 5 hours with his family. Please book a reservation for them."

# ── Teardown ────────────────────────────────────────────────────────────────

# AgentCore CLI v1.0.0-preview does not ship an `agentcore destroy`
# subcommand yet. Teardown is a three-step manual process — see the
# README for the exact AWS CLI and `cdk destroy` commands.
destroy:
	@echo "Teardown is manual. See README.md → Clean up."
	cd $(SCRIPTS_DIR) && $(PY) delete_lambdas.py

clean:
	rm -f $(STATE_FILE)
	@echo "Cleared $(STATE_FILE). To also remove the generated project, rm -rf $(PROJECT_DIR)/"
