/// <reference path="./.sst/platform/config.d.ts" />

export default $config({
  app(input) {
    return {
      name: "couple-todos-mcp",
      removal: input?.stage === "production" ? "retain" : "remove",
      home: "aws",
    };
  },
  async run() {
    // --- DynamoDB Table ---
    const table = new sst.aws.Dynamo("Todos", {
      fields: {
        id: "string",
      },
      primaryIndex: { hashKey: "id" },
    });

    // --- API Gateway ---
    const api = new sst.aws.ApiGatewayV2("McpApi", {
      cors: {
        allowOrigins: ["*"],
        allowHeaders: [
          "Content-Type",
          "Mcp-Session-Id",
          "Accept",
        ],
        allowMethods: ["GET", "POST", "DELETE", "OPTIONS"],
      },
    });

    // Single Lambda handles MCP transport (/mcp).
    const handler = {
      handler: "src/lambda.handler",
      link: [table],
      timeout: "30 seconds",
      memory: "512 MB",
      environment: {
        TABLE_NAME: table.name,
        COUPLE_NAMES: process.env.COUPLE_NAMES || "Person A,Person B",
      },
      // Include the Vite-built UI HTML in the Lambda bundle.
      // esbuild only bundles JS/TS — static assets need copyFiles.
      copyFiles: [{ from: "dist/src/client/mcp-app.html", to: "dist/src/client/mcp-app.html" }],
    };

    api.route("ANY /mcp", handler);

    return {
      url: api.url,
      tableName: table.name,
    };
  },
});
