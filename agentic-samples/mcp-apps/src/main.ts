// Local dev entry point. Starts the Express app on localhost.
// For Lambda deployment, use lambda.ts instead (via SST).
//
// Requires TABLE_NAME env var pointing to a DynamoDB table.
// Example: TABLE_NAME=couple-todos npm start

import { createApp } from "./server/app.js";

const PORT = parseInt(process.env.PORT || "3456");

const app = createApp();

app.listen(PORT, () => {
  console.log(`🏠 Couple Todos MCP server running on http://localhost:${PORT}`);
  console.log(`   MCP endpoint:  http://localhost:${PORT}/mcp`);
});
