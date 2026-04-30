import { createAmazonBedrock } from "@ai-sdk/amazon-bedrock";
import { fromNodeProviderChain } from "@aws-sdk/credential-providers";
import { ToolLoopAgent, tool, zodSchema } from "ai";
import { createServer, IncomingMessage, ServerResponse } from "node:http";
import { z } from "zod";

const bedrock = createAmazonBedrock({
  region: process.env.AWS_REGION ?? "us-east-1",
  credentialProvider: fromNodeProviderChain(),
});

const agent = new ToolLoopAgent({
  model: bedrock("global.anthropic.claude-sonnet-4-6"),
  instructions: "You are a helpful assistant. Use tools when appropriate.",
  tools: {
    add_numbers: tool({
      description: "Return the sum of two numbers.",
      inputSchema: zodSchema(z.object({
        a: z.number().int().describe("First number."),
        b: z.number().int().describe("Second number."),
      })),
      execute: async ({ a, b }) => a + b,
    }),
  },
  experimental_telemetry: { isEnabled: true },
});

function readBody(req: IncomingMessage): Promise<string> {
  return new Promise((resolve, reject) => {
    let data = "";
    req.on("data", (chunk) => (data += chunk));
    req.on("end", () => resolve(data));
    req.on("error", reject);
  });
}

const server = createServer(async (req: IncomingMessage, res: ServerResponse) => {
  if (req.method === "POST" && req.url === "/invocations") {
    try {
      const payload = JSON.parse(await readBody(req)) as { prompt?: string };
      const result = await agent.generate({ prompt: payload.prompt ?? "" });
      res.writeHead(200, { "Content-Type": "application/json" });
      res.end(JSON.stringify({ response: result.text }));
    } catch (err) {
      console.error("Invocation error:", err);
      res.writeHead(500, { "Content-Type": "application/json" });
      res.end(JSON.stringify({ error: String(err) }));
    }
  } else if (req.url === "/ping") {
    res.writeHead(200);
    res.end("OK");
  } else {
    res.writeHead(404);
    res.end();
  }
});

server.listen(8080, "0.0.0.0", () => {
  console.log("VercelAgent listening on http://0.0.0.0:8080/invocations");
});