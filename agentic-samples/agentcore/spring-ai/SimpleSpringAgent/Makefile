.PHONY: test stop deploy deploy-test destroy

CDK_DIR   = agentcore/cdk
CONTAINER = spring-agent-local
DOCKER   ?= docker

## test        — build Docker image and run tests against the local container
##              (override runtime: make test DOCKER=finch)
test:
	DOCKER=$(DOCKER) ./scripts/run-local.sh

## stop        — stop and remove the local test container (also stops Finch VM if DOCKER=finch)
stop:
	-$(DOCKER) stop $(CONTAINER)
	-$(DOCKER) rm   $(CONTAINER)
	@if [ "$(DOCKER)" = "finch" ]; then finch vm stop; fi

## deploy      — install CDK deps, compile TypeScript, and deploy to AWS
##              (override runtime: make deploy DOCKER=finch)
deploy:
	cd $(CDK_DIR) && npm install && npm run build && CDK_DOCKER=$(DOCKER) ./node_modules/.bin/cdk deploy --require-approval never

## deploy-test — deploy to AWS and run integration tests against the live runtime
##              (override runtime: make deploy-test DOCKER=finch)
deploy-test:
	DOCKER=$(DOCKER) ./scripts/test-ephemeral.sh

## destroy     — tear down the deployed AWS stack
destroy:
	cd $(CDK_DIR) && ./node_modules/.bin/cdk destroy
