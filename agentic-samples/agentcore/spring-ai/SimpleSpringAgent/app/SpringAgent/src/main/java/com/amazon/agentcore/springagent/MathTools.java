package com.amazon.agentcore.springagent;

import org.springframework.ai.tool.annotation.Tool;

public class MathTools {

    @Tool(description = "Return the sum of two numbers")
    public int addNumbers(int a, int b) {
        return a + b;
    }
}
