// Client-side logic running inside the sandboxed iframe.
// Bundled by Vite into a single-file HTML. Communicates with the MCP server
// exclusively through the host's postMessage bridge (callServerTool).

import { App } from "@modelcontextprotocol/ext-apps";

// Plain TS interface — we don't bundle Zod into the iframe.
interface Todo {
  id: string;
  title: string;
  description?: string;
  assignee: string;
  done: boolean;
  dueDate?: string;
  createdAt: string;
  updatedAt: string;
}

const app = new App({ name: "Couple Todos", version: "1.0.0" });

let todos: Todo[] = [];
let couple: string[] = [];

// Apply structured content from a tool result (either host-initiated or iframe-initiated).
function applyStructuredContent(sc: Record<string, unknown> | undefined) {
  if (!sc) return;
  if (sc.couple) couple = sc.couple as string[];
  if (sc.todos) {
    todos = sc.todos as Todo[];
    render();
  }
}

// `ontoolresult` fires when the host delivers a tool result (LLM-initiated).
app.ontoolresult = (result) => {
  applyStructuredContent(result.structuredContent as Record<string, unknown> | undefined);
};

await app.connect();

// `callServerTool` results don't trigger `ontoolresult`, so we handle the response directly.
async function refreshTodos() {
  try {
    const result = await app.callServerTool({ name: "list_todos", arguments: {} });
    applyStructuredContent((result as any).structuredContent);
  } catch (err) {
    console.error("Failed to refresh todos:", err);
  }
}

// --- Mutations ---

async function toggleTodo(id: string) {
  try {
    const todo = todos.find((t) => t.id === id);
    if (!todo) return;
    await app.callServerTool({
      name: "update_todo",
      arguments: { id, done: !todo.done },
    });
    await refreshTodos();
  } catch (err) {
    console.error("Failed to toggle todo:", err);
  }
}

async function updateTodoField(id: string, field: string, value: string) {
  try {
    await app.callServerTool({
      name: "update_todo",
      arguments: { id, [field]: value },
    });
    await refreshTodos();
  } catch (err) {
    console.error("Failed to update todo:", err);
  }
}

// --- Render ---

function todayStr(): string {
  return new Date().toISOString().slice(0, 10);
}

function duePillClass(dueDate: string): string {
  const today = todayStr();
  if (dueDate < today) return "overdue";
  if (dueDate === today) return "today";
  return "future";
}

function formatDate(iso: string): string {
  const d = new Date(iso + "T00:00:00");
  return d.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

function render() {
  const root = document.getElementById("app")!;
  root.innerHTML = "";

  // Header
  const header = document.createElement("div");
  header.className = "header";
  const h1 = document.createElement("h1");
  h1.textContent = "\uD83C\uDFE0 Our Todos";
  header.appendChild(h1);
  root.appendChild(header);

  // Board
  const board = document.createElement("div");
  board.className = "board";

  for (const person of couple) {
    const col = document.createElement("div");
    col.className = "column";

    // Column header
    const colHeader = document.createElement("div");
    colHeader.className = "column-header";
    colHeader.textContent = person;
    col.appendChild(colHeader);

    // Filter and sort todos for this person
    const personTodos = todos
      .filter((t) => t.assignee === person)
      .sort((a, b) => {
        // Not-done first, then done
        if (a.done !== b.done) return a.done ? 1 : -1;
        // Within same done status, sort by dueDate ascending (nulls last)
        if (!a.dueDate && !b.dueDate) return 0;
        if (!a.dueDate) return 1;
        if (!b.dueDate) return -1;
        return a.dueDate.localeCompare(b.dueDate);
      });

    // Cards
    for (const todo of personTodos) {
      col.appendChild(createCard(todo));
    }

    // Footer
    const doneCount = personTodos.filter((t) => t.done).length;
    const footer = document.createElement("div");
    footer.className = "column-footer";
    footer.textContent = `${doneCount}/${personTodos.length} done`;
    col.appendChild(footer);

    board.appendChild(col);
  }

  root.appendChild(board);
}

function createCard(todo: Todo): HTMLElement {
  const card = document.createElement("div");
  card.className = `card${todo.done ? " done" : ""}`;

  // Checkbox
  const checkbox = document.createElement("input");
  checkbox.type = "checkbox";
  checkbox.checked = todo.done;
  checkbox.addEventListener("change", () => toggleTodo(todo.id));
  card.appendChild(checkbox);

  // Content wrapper
  const content = document.createElement("div");
  content.className = "card-content";

  // Title
  const title = document.createElement("span");
  title.className = `title${todo.done ? " strike" : ""}`;
  title.textContent = todo.title;
  content.appendChild(title);

  // Description (click to edit inline)
  if (todo.description) {
    const desc = document.createElement("p");
    desc.className = "description";
    desc.textContent = todo.description;
    desc.addEventListener("click", () => {
      startEditingDescription(desc, todo);
    });
    content.appendChild(desc);
  }

  // Due date pill
  if (todo.dueDate) {
    const pill = document.createElement("span");
    pill.className = `due-pill ${duePillClass(todo.dueDate)}`;
    pill.textContent = `\uD83D\uDCC5 ${formatDate(todo.dueDate)}`;
    content.appendChild(pill);
  }

  card.appendChild(content);
  return card;
}

// --- Inline editing ---
// Click on the description <p> -> replace with a <textarea> prefilled with
// current text. On blur or Enter -> save via PATCH, re-render.
// On Escape -> cancel, re-render without saving.
function startEditingDescription(el: HTMLElement, todo: Todo) {
  const textarea = document.createElement("textarea");
  textarea.value = todo.description || "";
  textarea.className = "description";

  const save = () => {
    const newValue = textarea.value.trim();
    if (newValue !== todo.description) {
      updateTodoField(todo.id, "description", newValue);
    } else {
      render(); // re-render to restore original view
    }
  };

  textarea.addEventListener("blur", save);
  textarea.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      textarea.blur(); // triggers save via blur handler
    }
    if (e.key === "Escape") {
      textarea.removeEventListener("blur", save);
      render(); // cancel — re-render without saving
    }
  });

  el.replaceWith(textarea);
  textarea.focus();
  textarea.setSelectionRange(textarea.value.length, textarea.value.length);
}
