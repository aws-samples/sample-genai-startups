# Couple's Todo MCP App

This repository demonstrates how to build an MCP server with interactive UI capabilities, deployed to AWS Lambda. The project showcases the MCP Apps extension pattern, which enables rich, sandboxed web interfaces that communicate back to the MCP host through secure postMessage channels. This unlocks new possibilities for building collaborative, cloud-backed tools that integrate seamlessly with Claude and other MCP-compatible hosts.

## What we're building

A shared todo board for a couple, built as an [MCP](https://modelcontextprotocol.io/) server with an interactive UI using the [MCP Apps](https://www.npmjs.com/package/@modelcontextprotocol/ext-apps) extension.

The `list_todos` tool returns a two-column Kanban board rendered inside the MCP host (Claude Desktop, etc.) as a sandboxed iframe. Users can check/uncheck todos and edit descriptions directly in the board — the iframe invokes MCP tools (`update_todo`, `mark_done`, etc.) through the host's secure postMessage channel, with no separate API layer needed.

## Architecture

```
MCP Host (Claude Desktop, ChatGPT, etc.)
  |
  +-- Streamable HTTP --> API Gateway --> Lambda (Express)
  |                                        +-- POST /mcp      MCP transport (stateless)
  |
  +-- Sandboxed iframe --> board.html (Vite single-file bundle)
                             +-- Receives todos via structuredContent
                             +-- Mutations via callServerTool() (postMessage)
```

**Key design decisions:**

1. **Stateless Streamable HTTP transport** -- each Lambda invocation creates a fresh `McpServer` + `StreamableHTTPServerTransport`. No sessions, no SSE. Pure request/response, ideal for Lambda.

2. **postMessage for iframe mutations** -- the iframe uses `app.callServerTool()` from the MCP Apps SDK to invoke tools (`update_todo`, `mark_done`, etc.) through the host's secure postMessage channel.

3. **DynamoDB storage** for persistent todos.

## Project Structure

```
./
+-- sst.config.ts              SST infrastructure (DynamoDB + API Gateway + Lambda)
+-- vite.config.ts              Vite build (single-file HTML bundle)
+-- tsconfig.json               TypeScript config
+-- seed.ts                     Seed script for DynamoDB
+-- .env                        COUPLE_NAMES (not committed)
+-- src/
    +-- lambda.ts               Lambda entry point (serverless-http wrapper)
    +-- main.ts                 Local dev entry point
    +-- client/
    |   +-- mcp-app.html        UI shell (CSS + markup)
    |   +-- mcp-app.ts          Iframe logic (MCP Apps bridge, callServerTool, DOM rendering)
    +-- server/
        +-- app.ts              Express app factory (MCP transport)
        +-- server.ts           MCP server (tools + UI resource registration)
        +-- store.ts            DynamoDB CRUD operations
        +-- types.ts            Zod schemas (single source of truth for validation + types)
```

## MCP Tools

| Tool | Description | Returns UI? |
|------|-------------|:-----------:|
| `list_todos` | Show all todos as an interactive Kanban board | Yes |
| `add_todo` | Create a todo (title + assignee required, description + dueDate optional) | No |
| `update_todo` | Update a todo by ID (any field) | No |
| `delete_todo` | Delete a todo by ID | No |
| `mark_done` | Mark a todo as completed by ID | No |

## Prerequisites

- Node.js 18+
- AWS CLI configured with credentials
- SST CLI (`npm install -g sst` or use npx)

## Setup

```bash
# Install dependencies
npm install

# Create .env and configure the two person names
echo "COUPLE_NAMES=John,Jane" > .env
```

### Configure names

Set the `COUPLE_NAMES` environment variable to a comma-separated pair of names. This controls the board columns, assignee validation, and seed data:

```bash
# In .env
COUPLE_NAMES=John,Jane
```

If not set, it defaults to `Person A,Person B`.

## Deploy to AWS

```bash
# Build the UI + deploy infrastructure
npm run deploy

# Seed the DynamoDB table with sample data
TABLE_NAME=<table-name-from-sst-output> npx tsx seed.ts
```

SST outputs the API Gateway URL after deployment.

## Configure Claude Desktop

Use your mcp url with any compatible tool supporting MCP Apps. For Claude, visit the [connectors page](https://claude.ai/customize/connectors) and add a custom connector with your MCP url of the following format: `https://<api-gateway-id>.execute-api.<region>.amazonaws.com/mcp`


## Example Prompts

Once connected to the MCP host:

- **"Show me our todos"** -- renders the interactive Kanban board
- **"Add a todo for Person B: buy ski passes, due April 5"** -- creates a new todo (uses your configured names)
- **"Mark the grocery todo as done"** -- uses the ID from the previous list

## DynamoDB Data Model

| Attribute | Type | Description |
|-----------|------|-------------|
| `id` | String (PK) | UUID |
| `title` | String | Todo title |
| `description` | String | Optional details |
| `assignee` | String | One of the configured `COUPLE_NAMES` |
| `done` | Boolean | Completion state |
| `dueDate` | String | YYYY-MM-DD (optional) |
| `createdAt` | String | ISO datetime |
| `updatedAt` | String | ISO datetime |


## Tech Stack

- **MCP**: `@modelcontextprotocol/sdk` (Streamable HTTP transport), `@modelcontextprotocol/ext-apps` (UI rendering)
- **Server**: Express 5, `serverless-http`, Zod
- **Infrastructure**: SST (Ion), API Gateway v2, Lambda, DynamoDB
- **UI**: Vanilla TypeScript, bundled with Vite + `vite-plugin-singlefile`

## Cleanup

To cleanup the resources created, run `npx sst remove`.

---

> **⚠️ Security Notice: Sample Code**
> 
> This project is provided as sample code for demonstration purposes and is not production-ready. It is intended to illustrate MCP server patterns with AWS Lambda, API Gateway, and DynamoDB.