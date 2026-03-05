from bedrock_agentcore.runtime import BedrockAgentCoreApp
from claude_agent_sdk import query, ClaudeAgentOptions

app = BedrockAgentCoreApp()


@app.entrypoint
async def invoke(payload: dict) -> dict:
    prompt = payload.get("prompt", "")

    options = ClaudeAgentOptions(
        allowed_tools=["Read", "Bash", "Glob", "Grep"],
        permission_mode="acceptEdits",
    )

    final_result = ""
    async for message in query(prompt=prompt, options=options):
        if hasattr(message, "result"):
            final_result = message.result or ""

    return {"response": final_result}


if __name__ == "__main__":
    app.run()
