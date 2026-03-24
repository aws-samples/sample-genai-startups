#!/usr/bin/env python3
"""Cold Start Latency Test for AgentCore Runtime-to-Runtime MCP"""
import subprocess
import json
import time
import sys
import re

def invoke_agent(prompt):
    """Invoke agent and parse response"""
    start = time.time()
    result = subprocess.run(
        ["agentcore", "invoke", json.dumps({"prompt": prompt})],
        capture_output=True, text=True, cwd="/Users/sequdian/Documents/Repos/sample-genai-startups/kiro-agents/cold-start-test/agent"
    )
    e2e_time = time.time() - start
    
    # Extract JSON from output
    match = re.search(r'\{[^{}]*"mcp_result"[^{}]*\{[^{}]*\}[^{}]*\}', result.stdout)
    if match:
        try:
            response = json.loads(match.group())
            return {"success": True, "response": response, "e2e_ms": round(e2e_time * 1000)}
        except:
            pass
    
    return {"success": False, "error": result.stderr[:200], "e2e_ms": round(e2e_time * 1000)}

def run_test(label=""):
    """Run single test and print results"""
    print(f"\n{'='*50}")
    print(f"Test: {label}" if label else "Running test...")
    print(f"Time: {time.strftime('%H:%M:%S')}")
    
    result = invoke_agent(f"test {label}")
    
    if result["success"]:
        r = result["response"]
        mcp = r.get("mcp_result", {})
        print(f"✓ Success")
        print(f"  MCP Server uptime: {mcp.get('tool_result', 'N/A')}")
        print(f"  Connect:    {mcp.get('connect_ms', 'N/A'):>5}ms")
        print(f"  Init:       {mcp.get('init_ms', 'N/A'):>5}ms")
        print(f"  Tools load: {mcp.get('tools_load_ms', 'N/A'):>5}ms")
        print(f"  Tool call:  {mcp.get('tool_call_ms', 'N/A'):>5}ms")
        print(f"  Agent total:{r.get('total_request_ms', 'N/A'):>5}ms")
        print(f"  E2E:        {result['e2e_ms']:>5}ms")
        return mcp
    else:
        print(f"✗ Failed: {result.get('error', 'Unknown')}")
        return None

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "cold":
        # Single cold start test
        print("Running cold start test...")
        run_test("cold_start")
    else:
        # Multiple warm tests
        n = int(sys.argv[1]) if len(sys.argv) > 1 else 3
        results = []
        for i in range(n):
            r = run_test(f"warm_{i+1}")
            if r:
                results.append(r)
            time.sleep(1)
        
        if results:
            print(f"\n{'='*50}")
            print("Summary (warm tests):")
            print(f"  Avg connect:   {sum(r['connect_ms'] for r in results)//len(results)}ms")
            print(f"  Avg init:      {sum(r['init_ms'] for r in results)//len(results)}ms")
            print(f"  Avg tool call: {sum(r['tool_call_ms'] for r in results)//len(results)}ms")
