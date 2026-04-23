import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import {
  registerAppResource,
  registerAppTool,
  RESOURCE_MIME_TYPE,
} from "@modelcontextprotocol/ext-apps/server";
import { z } from "zod";
import fs from "node:fs/promises";
import path from "node:path";
import * as store from "./store.js";
import { PersonSchema, COUPLE } from "./types.js";

const DIST_DIR = path.join(process.cwd(), "dist", "src", "client");

export function createMcpServer(): McpServer {
  const server = new McpServer({
    name: "couple-todos",
    version: "1.0.0",
  });

  const boardUri = "ui://todos/board.html";

  // --- UI Resource ---
  // Serves the Vite-bundled single-file HTML.
  // This resource is STATIC — the same HTML is returned on every read, and may be
  // cached or preloaded by the host. Dynamic data (the current todo list, the
  // person names) is delivered separately via `structuredContent` in the tool
  // result. Do NOT try to inject per-request data into this HTML template.
  registerAppResource(server, "todo_board_ui", boardUri, {}, async () => {
    const html = await fs.readFile(
      path.join(DIST_DIR, "mcp-app.html"),
      "utf-8"
    );
    return {
      contents: [
        {
          uri: boardUri,
          mimeType: RESOURCE_MIME_TYPE,
          text: html,
        },
      ],
    };
  });

  // --- Tool: list_todos (with UI) ---
  // Returns the interactive Kanban board with all todos.
  // `structuredContent` serves double duty:
  //   1. The LLM reads `content` to narrate ("3 of 8 todos are done").
  //   2. The iframe receives `structuredContent` via postMessage (app.ontoolresult)
  //      and uses `todos` and `couple` to initialize the UI.
  registerAppTool(
    server,
    "list_todos",
    {
      title: "List Todos",
      description:
        "Show the couple's shared todo board. Returns an interactive UI with all todos organized by person.",
      inputSchema: {},
      _meta: {
        ui: {
          resourceUri: boardUri,
        },
      },
    },
    async () => {
      const todos = await store.getAllTodos();

      const doneCounts = {
        total: todos.length,
        done: todos.filter((t) => t.done).length,
      };

      const todoSummary = todos
        .map((t) => `- [${t.done ? "x" : " "}] ${t.title} (id: ${t.id}, assignee: ${t.assignee}${t.dueDate ? `, due: ${t.dueDate}` : ""})`)
        .join("\n");

      return {
        content: [
          {
            type: "text" as const,
            text: `${doneCounts.done}/${doneCounts.total} completed.\n\n${todoSummary}`,
          },
        ],
        structuredContent: {
          todos,
          couple: COUPLE,
        },
      };
    }
  );

  // --- Tool: add_todo ---
  // No UI — text-only response.
  server.registerTool(
    "add_todo",
    {
      title: "Add Todo",
      description: "Add a new todo for one of the couple.",
      inputSchema: {
        title: z.string().describe("Todo title"),
        assignee: PersonSchema.describe("Who this todo is for"),
        description: z.string().optional().describe("Optional details"),
        dueDate: z.string().optional().describe("Due date in YYYY-MM-DD format"),
      },
    },
    async ({ title, assignee, description, dueDate }) => {
      const todo = await store.addTodo({ title, assignee, description, dueDate });
      return {
        content: [
          {
            type: "text" as const,
            text: `Added "${todo.title}" for ${todo.assignee} (id: ${todo.id}).`,
          },
        ],
      };
    }
  );

  // --- Tool: update_todo ---
  server.registerTool(
    "update_todo",
    {
      title: "Update Todo",
      description: "Update an existing todo by ID.",
      inputSchema: {
        id: z.string().describe("Todo ID"),
        title: z.string().optional(),
        description: z.string().optional(),
        assignee: PersonSchema.optional(),
        done: z.boolean().optional(),
        dueDate: z.string().optional(),
      },
    },
    async ({ id, ...updates }) => {
      const todo = await store.updateTodo(id, updates);
      if (!todo) {
        return {
          content: [{ type: "text" as const, text: `Todo ${id} not found.` }],
          isError: true,
        };
      }
      return {
        content: [
          { type: "text" as const, text: `Updated "${todo.title}".` },
        ],
      };
    }
  );

  // --- Tool: delete_todo ---
  server.registerTool(
    "delete_todo",
    {
      title: "Delete Todo",
      description: "Delete a todo by ID.",
      inputSchema: {
        id: z.string().describe("Todo ID"),
      },
    },
    async ({ id }) => {
      const deleted = await store.deleteTodo(id);
      return {
        content: [
          {
            type: "text" as const,
            text: deleted ? `Deleted todo ${id}.` : `Todo ${id} not found.`,
          },
        ],
      };
    }
  );

  // --- Tool: mark_done ---
  server.registerTool(
    "mark_done",
    {
      title: "Mark Todo Done",
      description: "Mark a todo as completed by ID.",
      inputSchema: {
        id: z.string().describe("Todo ID"),
      },
    },
    async ({ id }) => {
      const todo = await store.updateTodo(id, { done: true });
      if (!todo) {
        return {
          content: [{ type: "text" as const, text: `Todo ${id} not found.` }],
          isError: true,
        };
      }
      return {
        content: [
          { type: "text" as const, text: `Marked "${todo.title}" as done.` },
        ],
      };
    }
  );

  return server;
}
