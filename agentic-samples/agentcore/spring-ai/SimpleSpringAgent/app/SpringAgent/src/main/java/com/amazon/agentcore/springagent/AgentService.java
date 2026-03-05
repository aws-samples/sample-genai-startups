package com.amazon.agentcore.springagent;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.ai.chat.client.ChatClient;
import org.springframework.stereotype.Service;
import org.springaicommunity.agentcore.annotation.AgentCoreInvocation;
import org.springaicommunity.agentcore.context.AgentCoreContext;
import org.springaicommunity.agentcore.context.AgentCoreHeaders;

@Service
public class AgentService {

    private static final Logger log = LoggerFactory.getLogger(AgentService.class);

    private final ChatClient chatClient;

    public AgentService(ChatClient.Builder builder) {
        this.chatClient = builder.defaultTools(new MathTools()).build();
    }

    @AgentCoreInvocation
    public String handlePrompt(PromptRequest request, AgentCoreContext context) {
        log.info("Session: {}", context.getHeader(AgentCoreHeaders.SESSION_ID));
        return chatClient.prompt().user(request.prompt()).call().content();
    }
}
