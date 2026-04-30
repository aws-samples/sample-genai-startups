import express from "express";
import cors from "cors";
import { StreamableHTTPServerTransport } from "@modelcontextprotocol/sdk/server/streamableHttp.js";
import { createMcpServer } from "./server.js";

function forceHeader(
  req: express.Request,
  name: "accept" | "content-type",
  value: string,
) {
  req.headers[name] = value; // nosemgrep: remote-property-injection
  const rawIdx = req.rawHeaders.findIndex((h) => h.toLowerCase() === name);
  if (rawIdx !== -1) {
    req.rawHeaders[rawIdx + 1] = value;
  } else {
    req.rawHeaders.push(name.charAt(0).toUpperCase() + name.slice(1), value);
  }
}

export function createApp() {
  const app = express();
  app.use(cors());
  app.use(express.json());
  app.post("/mcp", async (req, res) => {

    forceHeader(req, "accept", "application/json, text/event-stream");
    forceHeader(req, "content-type", "application/json");

    try {
      const mcpServer = createMcpServer();
      const transport = new StreamableHTTPServerTransport({
        sessionIdGenerator: undefined,
        enableJsonResponse: true,
      });

      res.on("close", () => {
        transport.close();
        mcpServer.close();
      });

      await mcpServer.connect(transport);
      await transport.handleRequest(req, res, req.body);
    } catch (err) {
      console.error("MCP POST error:", err);
      if (!res.headersSent) {
        res.status(500).json({ error: (err as Error).message });
      }
    }
  });

  app.get("/mcp", (_req, res) => {
    res.status(405).json({ error: "Method not allowed (stateless mode)" });
  });

  app.delete("/mcp", (_req, res) => {
    res.status(405).json({ error: "Method not allowed (stateless mode)" });
  });

  return app;
}
