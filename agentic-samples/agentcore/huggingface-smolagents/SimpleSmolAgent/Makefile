.PHONY: install dev test deploy invoke status

APP_DIR = app/Smolagent

## install  — install Python dependencies via uv
install:
	cd $(APP_DIR) && uv sync

## dev      — start local development server on port 8080
dev:
	agentcore dev

## test     — invoke the local agent with demo prompts
##            (requires `make dev` running in another terminal)
test:
	agentcore invoke "What is 42 plus 58?"
	agentcore invoke "What is the capital of France?"

## deploy   — package and deploy to AWS via AgentCore CLI
deploy:
	agentcore deploy

## invoke   — invoke the deployed agent with a demo prompt
invoke:
	agentcore invoke "What is 42 plus 58?"

## status   — show the current deployment status
status:
	agentcore status
