#!/usr/bin/env npx tsx
// Seed script — run manually to populate the DynamoDB table with sample data.
// Usage: TABLE_NAME=couple-todos npx tsx seed.ts

import "dotenv/config";
import crypto from "node:crypto";
import { DynamoDBClient } from "@aws-sdk/client-dynamodb";
import { DynamoDBDocumentClient, PutCommand, ScanCommand } from "@aws-sdk/lib-dynamodb";

const TABLE_NAME = process.env.TABLE_NAME;
if (!TABLE_NAME) {
  console.error("ERROR: TABLE_NAME env var is required");
  process.exit(1);
}

const docClient = DynamoDBDocumentClient.from(new DynamoDBClient({}), {
  marshallOptions: { removeUndefinedValues: true },
});

function isoDate(daysFromNow: number): string {
  const d = new Date();
  d.setDate(d.getDate() + daysFromNow);
  return d.toISOString().slice(0, 10);
}

// Check if table already has data
const check = await docClient.send(
  new ScanCommand({ TableName: TABLE_NAME, Limit: 1 })
);
if (check.Items && check.Items.length > 0) {
  console.log("Table already has data — skipping seed.");
  process.exit(0);
}

const dayOfWeek = new Date().getDay();
const daysUntilSaturday = (6 - dayOfWeek + 7) % 7 || 7;
const daysUntilSunday = (7 - dayOfWeek + 7) % 7 || 7;
const ts = new Date().toISOString();

const coupleNames = (process.env.COUPLE_NAMES || "Person A,Person B")
  .split(",")
  .map((n) => n.trim())
  .filter(Boolean);
const [personA, personB] = coupleNames;

const samples = [
  { title: "Weekly grocery run", assignee: personA, done: false, dueDate: isoDate(daysUntilSaturday) },
  { title: "Schedule dentist appointment", assignee: personB, done: false, description: "Check if Dr. Patel has openings next month" },
  { title: "Book restaurant for anniversary", assignee: personA, done: false, dueDate: isoDate(10), description: "That Italian place on 5th we liked" },
  { title: "Fix leaky kitchen faucet", assignee: personA, done: false, description: "Washer replacement — hardware store first" },
  { title: "Buy birthday gift for nephew", assignee: personB, done: false, dueDate: isoDate(5), description: "He's into dinosaurs and Lego" },
  { title: "Plan weekend hike route", assignee: personB, done: false, dueDate: isoDate(daysUntilSunday), description: "Maybe the ridge trail?" },
  { title: "Renew car insurance", assignee: personA, done: false, dueDate: isoDate(3), description: "Policy expires soon — compare quotes" },
  { title: "Order new living room curtains", assignee: personB, done: true, description: "Went with the linen ones from West Elm" },
];

await Promise.all(
  samples.map((s) =>
    docClient.send(
      new PutCommand({
        TableName: TABLE_NAME,
        Item: {
          id: crypto.randomUUID(),
          createdAt: ts,
          updatedAt: ts,
          ...s,
        },
      })
    )
  )
);

console.log(`Seeded ${samples.length} todos into ${TABLE_NAME}`);
