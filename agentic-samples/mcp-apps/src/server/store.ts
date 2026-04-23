import crypto from "node:crypto";
import { DynamoDBClient } from "@aws-sdk/client-dynamodb";
import {
  DynamoDBDocumentClient,
  PutCommand,
  GetCommand,
  DeleteCommand,
  ScanCommand,
} from "@aws-sdk/lib-dynamodb";
import { Todo, CreateTodoInput, UpdateTodoInput } from "./types.js";

const TABLE_NAME = process.env.TABLE_NAME || "couple-todos";

const ddbClient = new DynamoDBClient({});
const docClient = DynamoDBDocumentClient.from(ddbClient, {
  marshallOptions: { removeUndefinedValues: true },
});

function now(): string {
  return new Date().toISOString();
}

// --- CRUD operations ---

export async function getAllTodos(): Promise<Todo[]> {
  const result = await docClient.send(new ScanCommand({ TableName: TABLE_NAME }));
  return (result.Items || []) as Todo[];
}

export async function getTodoById(id: string): Promise<Todo | undefined> {
  const result = await docClient.send(
    new GetCommand({ TableName: TABLE_NAME, Key: { id } })
  );
  return result.Item as Todo | undefined;
}

export async function addTodo(input: CreateTodoInput): Promise<Todo> {
  const ts = now();
  const item = {
    id: crypto.randomUUID(),
    done: false,
    createdAt: ts,
    updatedAt: ts,
    title: input.title,
    assignee: input.assignee,
    description: input.description,
    dueDate: input.dueDate,
  };
  await docClient.send(new PutCommand({ TableName: TABLE_NAME, Item: item }));
  return item as Todo;
}

export async function updateTodo(
  id: string,
  updates: UpdateTodoInput
): Promise<Todo | undefined> {
  const existing = await getTodoById(id);
  if (!existing) return undefined;

  const merged = {
    ...existing,
    ...updates,
    done: updates.done ?? existing.done,
    updatedAt: now(),
  };
  await docClient.send(new PutCommand({ TableName: TABLE_NAME, Item: merged }));
  return merged as Todo;
}

export async function deleteTodo(id: string): Promise<boolean> {
  const existing = await getTodoById(id);
  if (!existing) return false;
  await docClient.send(
    new DeleteCommand({ TableName: TABLE_NAME, Key: { id } })
  );
  return true;
}
