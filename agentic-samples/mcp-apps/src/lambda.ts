// AWS Lambda entry point.
// Wraps our Express app with serverless-http so it can run behind API Gateway.
// The MCP transport runs in STATELESS mode (no sessions, JSON responses)
// because Lambda invocations are ephemeral — no in-memory session state.

import serverless from "serverless-http";
import { createApp } from "./server/app.js";

const app = createApp();
const serverlessHandler = serverless(app);

export const handler = async (event: any, context: any) => {
  return serverlessHandler(event, context);
};
