import { z } from "zod";

// Names are configurable via the COUPLE_NAMES env var (comma-separated).
// Defaults to "Person A,Person B" when not set.
const names = (process.env.COUPLE_NAMES || "Person A,Person B")
  .split(",")
  .map((n) => n.trim())
  .filter(Boolean) as [string, ...string[]];

export const PersonSchema = z.enum(names);
export type Person = z.infer<typeof PersonSchema>;
export const COUPLE = PersonSchema.options;

// Full todo shape — used for type inference across server code.
export const TodoSchema = z.object({
  id: z.string(),
  title: z.string(),
  description: z.string().optional(),
  assignee: PersonSchema,
  done: z.boolean(),
  dueDate: z.string().optional(),
  createdAt: z.string(),
  updatedAt: z.string(),
});
export type Todo = z.infer<typeof TodoSchema>;

// Validated input for creating a new todo.
export const CreateTodoSchema = z.object({
  title: z.string(),
  assignee: PersonSchema,
  description: z.string().optional(),
  dueDate: z.string().optional(),
});
export type CreateTodoInput = z.infer<typeof CreateTodoSchema>;

// Partial fields for updating an existing todo.
export const UpdateTodoSchema = z.object({
  title: z.string().optional(),
  description: z.string().optional(),
  assignee: PersonSchema.optional(),
  done: z.boolean().optional(),
  dueDate: z.string().optional(),
});
export type UpdateTodoInput = z.infer<typeof UpdateTodoSchema>;
