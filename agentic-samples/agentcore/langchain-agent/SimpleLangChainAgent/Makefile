.PHONY: install dev test deploy invoke status

APP_DIR = app/LangChainAgent

## install  — install Python dependencies
install:
	cd $(APP_DIR) && uv sync

## dev      — start local development server on port 8080
dev:
	agentcore dev

## test     — invoke local agent with demo prompts (requires dev server running)
test:
	agentcore invoke "What is 42 plus 58?"
	agentcore invoke "What is the capital of France?"

## deploy   — package and deploy to AWS
deploy:
	agentcore deploy

## invoke   — invoke the deployed agent
invoke:
	agentcore invoke "What is 42 plus 58?"

## status   — show deployment status
status:
	agentcore status
