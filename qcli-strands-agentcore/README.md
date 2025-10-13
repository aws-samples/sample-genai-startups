# Q CLI Strands AgentCore Agent

An [Amazon Q Developer CLI custom agent](https://docs.aws.amazon.com/amazonq/latest/qdeveloper-ug/command-line-custom-agents.html) specialized in [Strands](https://strandsagents.com/latest/) and [Amazon Bedrock AgentCore](https://aws.amazon.com/bedrock/agentcore/) development. This agent is equiped with tools, MCP servers, agent steering files, and a knowledge base to ensure agents are developed following best practices.

> **⚠️ IMPORTANT DISCLAIMER**  
> This solutions uses Generative AI. Always review all code, actions, and decisions before using in production environments. Verify that generated code meets your security, performance, and business requirements.

## Install Amazon Q Developer CLI

1. Install and access Q CLI following the instructions [here](https://docs.aws.amazon.com/amazonq/latest/qdeveloper-ug/command-line-installing.html)
2. Verify installation
   ```bash
   q --version
   ```

## Agent Setup

1. **Clone the repository**

2. **Review agent configuration**
   - Check agent config file in `qcli-strands-agentcore/.amazonq/cli-agents/strands-agentcore-agent.json`
   - To understand the schema of this file, please read this [doc](https://github.com/aws/amazon-q-developer-cli/blob/main/docs/agent-format.md)

3. **Review agent rules**
   - Check files in `qcli-strands-agentcore/.amazonq/rules/`
   - These files steer the agent to follow best practices for Strands and AgentCore 

4. **Add agent config to your project workspace**
   
   Copy the `.amazonq` directory located in the `qcli-strands-agentcore` directory and store in the root of your project workspace as seen below:
   ```
   my-project/
   ├── .amazonq/
   │       └── cli-agents/
   │       |   └── strands-agentcore-agent.json
   │       └── rules/
   └── src/
      └── main.py
   ```



5. **[OPTIONAL] Clone sample repositories to use as a knowledge base for the agent. This can help provide more accurate code suggestions**
   ```bash
   # Create directory to store sample repos
   mkdir agentic-doc-samples

   cd agentic-doc-samples

   # Clone official AWS Samples repos for Strands and AgentCore
   git clone https://github.com/strands-agents/samples
   git clone https://github.com/awslabs/amazon-bedrock-agentcore-samples

   # Rename 'samples' dir to 'strands-samples' for readability
   mv samples strands-samples

   ```

   >Note: The `agentic-doc-samples` directory can be located inside or outside of your project. 


6. **[OPTIONAL] Create a [Q CLI knowledge base](https://github.com/aws/amazon-q-developer-cli/blob/main/docs/knowledge-management.md) for the agent to search and look up Strands/AgentCore samples and docs. This can help the agent provide more accurate code suggestions**

   This gives the agent a local Retrieval Augmented Generation (RAG)/knowledge base functionality allowing you to search and look up contextual information that persists across chat sessions, protecting the context window.

   * Ensure you are in the root of your project directory
   * Turn on Knowledge feature (this feature is experiemental and requires activation)
   ```bash
   q settings chat.enableKnowledge true
   ```
   * Launch the agent
   ```bash
   q chat --agent strands-agentcore-agent
   ```
    * Create the knowledge base
   ```bash
   /knowledge add 'path-to-agentic-docs-samples-dir'

   # Example
   /knowledge add agentic-doc-samples/
   ```
    * Verify successful indexing (this does take a few minutes)
   ```bash
   /knowledge status

   👤 Agent (strands-agentcore-agent):
      📂 agentic-docs-samples/ (e663324b)
         Knowledge context for agentic-docs-samples/
         1756 items • Best • 09/30 19:51
   ```
   * Close the Q CLI chat session to start a fresh session
   ```bash
   /quit
   ```

7. **Ensure AWS MCP server dependencies are installed**
   - Install `uv` from [Astral](https://docs.astral.sh/uv/getting-started/installation/)
   - Install `python` using `uv python install`
   - Read more about AWS MCP servers [here](https://awslabs.github.io/mcp/)


## Usage

1. **Ensure you are in the root of your project**


2. **Launch the agent**
   ```bash
   q chat --agent strands-agentcore-agent
   ```

3. **Test the agent and its MCP server integrations**
   ```bash
   What is Amazon Bedrock Agentcore?
   ```
   ```bash
   How do I build an agent using Strands? 

   ```
4. **Test the agent's knowledge base containing code samples**
   ```bash
   Using the knowledge tool, show me examples of agents using strands and agentcore
   ```

   >Note: The `knowledge tool` will only work if you have created a knowledge base 


5. **Example prompt to build Agent App**
   ```bash
   
   Build a generative AI project planner agent using strands and agentcore with a chatbot UI for task management inside a new directory called 'agent-app'. Functionality must include the creation, update, view, and tracking of tasks through a conversational interface. Allow for local deployment. Ensure the following libraries are used:

      1. strands-agents
      2. strands-agents-tools
      3. flask
      4. flask-cors
      5. boto3
      6. bedrock-agentcore
      7. bedrock-agentcore-starter-toolkit

   ```
