# Store active workflows in memory (in a real-world application, this should be in a database or Redis)
import datetime
from typing import Dict, Any, Optional
import uuid
from models import Workflow, WorkflowNode, WorkflowEdge, Agent, Tool, AgentTool
import json
import importlib
import uuid
from typing import Dict, Any, Optional, List
import boto3
import rapidjson
# Import Strands classes or create mock implementations
from multiprocessing import Manager, Process, Queue
from strands import Agent as StrandsAgent, tool
from strands.tools.mcp import MCPClient
from mcp import stdio_client, StdioServerParameters
import re
import os
from strands.types.tools import ToolResult, ToolUse

# Import all tools from strands_tools
from strands_tools import (
    file_read,
    file_write,
    editor,
    shell,
    http_request,
    python_repl,
    calculator,
    use_aws,
    retrieve,
    nova_reels,
    memory,
    environment,
    generate_image,
    image_reader,
    journal,
    think,
    load_tool,
    swarm,
    current_time,
    sleep,
    agent_graph,
    cron,
    slack,
    speak,
    stop,
    use_llm,
    workflow,
    batch
)


@tool
def think_tool(thought: str, cycle_count: int, system_prompt: str, agent: Any) -> Dict[str, Any]:
    """
    Recursive thinking tool for sophisticated thought generation, learning, and self-reflection.

    This tool implements a multi-cycle cognitive analysis approach that progressively refines thoughts
    through iterative processing. Each cycle builds upon insights from the previous cycle,
    creating a depth of analysis that would be difficult to achieve in a single pass.

    How It Works:
    ------------
    1. The tool processes the initial thought through a specified number of thinking cycles
    2. Each cycle uses the output from the previous cycle as a foundation for deeper analysis
    3. A specialized system prompt guides the thinking process toward specific expertise domains
    4. Each cycle's output is captured and included in the final comprehensive analysis
    5. The tool avoids recursive self-calls and encourages the use of other tools when appropriate

    Thinking Process:
    ---------------
    - First cycle processes the original thought directly with the provided system prompt
    - Each subsequent cycle builds upon the previous cycle's output
    - Cycles are tracked and labeled clearly in the output
    - The process creates a chain of progressive refinement and deeper insights
    - Final output includes the complete thought evolution across all cycles

    Common Usage Scenarios:
    ---------------------
    - Problem analysis: Breaking down complex problems into manageable components
    - Idea development: Progressively refining creative concepts
    - Learning exploration: Generating questions and insights about new domains
    - Strategic planning: Developing multi-step approaches to challenges
    - Self-reflection: Analyzing decision processes and potential biases

    Args:
        thought: The detailed thought or idea to process through multiple thinking cycles.
            This can be a question, statement, problem description, or creative prompt.
        cycle_count: Number of thinking cycles to perform (1-10). More cycles allow for
            deeper analysis but require more time and resources. Typically 3-5 cycles
            provide a good balance of depth and efficiency.
        system_prompt: Custom system prompt to use for the LLM thinking process. This should
            specify the expertise domain and thinking approach for processing the thought.
        **kwargs: Additional keyword arguments passed to the underlying LLM processing.

    Returns:
        Dict containing status and response content in the format:
        {
            "status": "success|error",
            "content": [{"text": "Detailed thinking output across all cycles"}]
        }

        Success case: Returns concatenated results from all thinking cycles
        Error case: Returns information about what went wrong during processing

    Notes:
        - Higher cycle counts provide deeper analysis but consume more resources
        - The system_prompt significantly influences the thinking style and domain expertise
        - For complex topics, more specific system prompts tend to yield better results
        - The tool is designed to avoid recursive self-calls that could cause infinite loops
        - Each cycle has visibility into previous cycle outputs to enable building upon insights
    """
    try:
        return think.think(thought, cycle_count, system_prompt+". Be very concise. You MUST not provide an answer, only self reflection." , agent=None)
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise(e)
    
@tool
def use_llm_tool(tool: ToolUse, **kwargs: Any) -> ToolResult:
    """
    Create a new LLM instance using the Agent interface.

    This function creates a new Strands Agent instance with the provided system prompt,
    runs it with the specified prompt, and returns the response with performance metrics.
    It allows for isolated processing in a fresh context separate from the main agent.

    How It Works:
    ------------
    1. The function initializes a new Agent instance with the provided system prompt
    2. The agent processes the given prompt in its own isolated context
    3. The response and metrics are captured and returned in a structured format
    4. The new agent instance exists only for the duration of this function call

    Agent Creation Process:
    ---------------------
    - A fresh Agent object is created with an empty message history
    - The provided system prompt configures the agent's behavior and capabilities
    - The agent processes the prompt in its own isolated context
    - Response and metrics are captured for return to the caller
    - The parent agent's callback_handler is used if one is not specified

    Common Use Cases:
    ---------------
    - Task delegation: Creating specialized agents for specific subtasks
    - Context isolation: Processing prompts in a clean context without history
    - Multi-agent systems: Creating multiple agents with different specializations
    - Learning and reasoning: Using nested agents for complex reasoning chains

    Args:
        tool (ToolUse): Tool use object containing the following:
            - prompt (str): The prompt to process with the new agent instance
            - system_prompt (str, optional): Custom system prompt for the agent
        **kwargs (Any): Additional keyword arguments

    Returns:
        ToolResult: Dictionary containing status and response content in the format:
        {
            "toolUseId": "unique-tool-use-id",
            "status": "success",
            "content": [
                {"text": "Response: The response text from the agent"},
                {"text": "Metrics: Performance metrics information"}
            ]
        }

    Notes:
        - The agent instance is temporary and will be garbage-collected after use
        - The agent(prompt) call is synchronous and will block until completion
        - Performance metrics include token usage and processing latency information
    """
    return use_llm.use_llm(tool, kwargs)


def _processing_thread(workflow_context, input_queue: Queue, output_queue: Queue, log_queue: Queue):
    print(f"[WORKFLOW_LOG] Starting processing thread for workflow: {workflow_context.get('name', 'Unknown')}")

    def top_level_callback_handler(**event):
        if "delta" in event:
            #remove properties that arent data or delta
            event = {k: v for k, v in event.items() if k in ["delta", 'current_tool_use']}
            

            output_queue.put("data: " + json.dumps(event, default=str) + "\nend")
    def agent_level_callback_handler(**event):

        if "delta" in event:
            event = {k: v for k, v in event.items() if k in ["delta",'current_tool_use']}

            if 'text' in event['delta']:
                event['delta'] = {'toolUse':{'input':event['delta']['text']}}
                event['current_tool_use'] = {'toolUseId':'agent', 'name': 'aws_documentation_retriever'}
            
            output_queue.put("data: " + json.dumps(event, default=str) + "\nend")


    print(f"[WORKFLOW_LOG] Creating nodes for processing thread...")
    agents = WorkflowRunner.create_nodes(workflow_context, log_queue)
    workflow_context['agents'] = agents
    print(f"[WORKFLOW_LOG] Created {len(agents)} agents in processing thread")
    if len(agents) > 1:
        print(f"[WORKFLOW_LOG] Multiple agents detected, creating orchestrator")
        # Create an orchestrator agent that manages the workflow
        
        for i, agent in enumerate(agents):
            agent.callback_handler = agent_level_callback_handler
            print(f"[WORKFLOW_LOG] Agent {i}: {getattr(agent, '__agent_name', 'Unknown')} has {len(agent.tools) if hasattr(agent, 'tools') else 0} tools")
        
        orchestrator = WorkflowRunner._create_orchestrator(workflow_context, log_queue)
        orchestrator.callback_handler = top_level_callback_handler
        workflow_context['orchestrator'] = orchestrator
        print(f"[WORKFLOW_LOG] Created orchestrator with {len(orchestrator.tools) if hasattr(orchestrator, 'tools') else 0} tools")
    else:
        print(f"[WORKFLOW_LOG] Single agent mode, using agent as orchestrator")
        orchestrator = agents[0]
        orchestrator.callback_handler = top_level_callback_handler
        workflow_context['orchestrator'] = orchestrator
        print(f"[WORKFLOW_LOG] Orchestrator agent: {getattr(orchestrator, '__agent_name', 'Unknown')} has {len(orchestrator.tools) if hasattr(orchestrator, 'tools') else 0} tools")
        
    
    print(f"[WORKFLOW_LOG] Processing thread setup complete, sending started signal")
    output_queue.put("_Q_E_E_STARTED")
    #loop input queue gets until receive a _Q_E_E_TERMINATE message
    while True:
        try:
            message = input_queue.get()
        except Exception as e:
            print(f"[WORKFLOW_LOG] Exception getting message from input queue: {str(e)}")
            break
        print(f"[WORKFLOW_LOG] Processing thread received message: {message[:50]}..." if len(str(message)) > 50 else f"[WORKFLOW_LOG] Processing thread received message: {message}")
        if message == "_Q_E_E_TERMINATE":
            print(f"[WORKFLOW_LOG] Processing thread terminating")
            break
        elif message == "_Q_E_E_RETRIEVE":
            # Retrieve and send conversation history
            history = workflow_context.get('conversation_history', [])
            history_json = json.dumps(history, default=str)
            output_queue.put("_Q_E_E_HISTORY" + history_json)
        else:
            # Add message to conversation history
            if 'conversation_history' not in workflow_context:
                workflow_context['conversation_history'] = []
            workflow_context['conversation_history'].append({
                'role': 'user',
                'content': message,
                'timestamp': json.dumps(datetime.datetime.now(datetime.timezone.utc), default=str)
            })
            
            answer = orchestrator(message)
            
            # Add response to conversation history
            workflow_context['conversation_history'].append({
                'role': 'assistant', 
                'content': str(answer),
                'timestamp': json.dumps(datetime.datetime.now(datetime.timezone.utc), default=str)
            })

            output_queue.put("_Q_E_E_ANSWERED")
    pass

class WorkflowRunner:
    """
    Class responsible for managing workflow instances and handling message delivery
    between the chat interface and the workflow.
    """
    # Global dictionary to store workflow contexts by session_id
    _workflow_contexts = {}
    # Dictionary to track workflow edit timestamps
    _workflow_edit_timestamps = {}


 
    @classmethod
    def create_threaded_workflow(cls, workflow_id: uuid.UUID, db_session, input_queue, output_queue, log_queue):
        workflow = cls.load_workflow(workflow_id, db_session)
        if not workflow:
            raise ValueError(f"Workflow with ID {workflow_id} not found")
                    


        process = Process(target=_processing_thread, args=(workflow, input_queue, output_queue, log_queue))
        process.start()
        return workflow['name']

    @classmethod
    def create_threaded_agent(cls, agent_id: uuid.UUID, db_session, input_queue, output_queue, log_queue):
        agent_context = cls.load_agent(agent_id, db_session)
        if not agent_context:
            print(f"AGENT CONTEXT NOT FOUND FOR ID {agent_id}")
            raise ValueError(f"Agent with ID {agent_id} not found")
        print("AGENT CONTEXT", json.dumps(agent_context, indent=2, default=str))
        process = Process(target=_processing_thread, args=(agent_context, input_queue, output_queue, log_queue))
        print("STARTING PROCESS")
        try:
            process.start()
        except Exception as e:
            import traceback
            traceback.print_exc()
            print("PROCESS FAILED TO START")
            raise(e)
        print("PROCESS STARTED")
        return agent_context['name']


    @classmethod
    def get_active_workflow(cls, session_id: str = None) -> Optional[Dict[str, Any]]:
        """
        Get the currently active workflow from the session ID.
        
        Args:
            session_id: The session ID to look up
            
        Returns:
            Dict containing workflow data if one is active, None otherwise
        """
        if not session_id:
            return None
        
        # Get workflow context from global dictionary
        return cls._workflow_contexts.get(session_id)
    
    @classmethod
    def load_workflow(cls, workflow_id: uuid.UUID, db_session) -> Dict[str, Any]:
        """
        Load workflow data from database without initializing agents/tools.
        
        Args:
            workflow_id: ID of the workflow to load
            db_session: SQLAlchemy database session
            
        Returns:
            Dict containing the workflow data structure
        """
        # Load the workflow from the database
        workflow = db_session.query(Workflow).get(workflow_id)
        if not workflow:
            raise ValueError(f"Workflow with ID {workflow_id} not found")
            
        nodes = db_session.query(WorkflowNode).filter_by(workflow_id=workflow_id).all()
        edges = db_session.query(WorkflowEdge).filter_by(workflow_id=workflow_id).all()
        
        # Prepare node data with all database references resolved
        prepared_nodes = {}
        for node in nodes:
            node_data = {
                'id': node.id,
                'type': node.node_type,
                'position': {'x': node.position_x, 'y': node.position_y}
            }
            
            # Add reference data based on node type
            if node.node_type == 'agent' and node.reference_id:
                agent = db_session.query(Agent).get(node.reference_id)
                if agent:
                    # Get all tools associated with this agent
                    agent_tool_associations = db_session.query(AgentTool).filter_by(agent_id=agent.id).all()
                    agent_tools = []
                    for assoc in agent_tool_associations:
                        tool = db_session.query(Tool).get(assoc.tool_id)
                        if tool:
                            agent_tools.append({
                                'id': tool.id,
                                'name': tool.name,
                                'tool_type': tool.tool_type,
                                'config': tool.config,
                                'agent_id': tool.agent_id
                            })
                    
                    node_data['reference'] = {
                        'id': agent.id,
                        'name': agent.name,
                        'prompt': agent.prompt,
                        'model_id': agent.model_id,
                        'description': agent.description,
                        'tools': agent_tools
                    }
            elif node.node_type == 'tool' and node.reference_id:
                tool = db_session.query(Tool).get(node.reference_id)
                if tool:
                    node_data['reference'] = {
                        'id': tool.id,
                        'name': tool.name,
                        'tool_type': tool.tool_type,
                        'config': tool.config,
                        'agent_id': tool.agent_id
                    }
            
            prepared_nodes[node.id] = node_data
        
        # Build workflow context with all data needed for initialization
        workflow_data = {
            'id': workflow.id,
            'name': workflow.name,
            'description': workflow.description,
            'model_id': workflow.model_id,
            'nodes': prepared_nodes,
            'edges': [{'source': edge.source_node_id, 'target': edge.target_node_id} for edge in edges],
            'conversation_history': [],
            'last_edited': getattr(workflow, 'last_edited', None)
        }
        
        return workflow_data
    
    @classmethod
    def load_agent(cls, agent_id: uuid.UUID, db_session) -> Dict[str, Any]:
        """
        Load agent data from database and create a minimal workflow context.
        
        Args:
            agent_id: ID of the agent to load
            db_session: SQLAlchemy database session
            
        Returns:
            Dict containing the agent data in workflow context format
        """
        # Load the agent from the database
        agent_db = db_session.query(Agent).get(agent_id)
        if not agent_db:
            raise ValueError(f"Agent with ID {agent_id} not found")
        
        # Get all tools associated with this agent
        agent_tool_associations = db_session.query(AgentTool).filter_by(agent_id=agent_db.id).all()
        agent_tools = []
        for assoc in agent_tool_associations:
            tool = db_session.query(Tool).get(assoc.tool_id)
            if tool:
                agent_tools.append({
                    'id': tool.id,
                    'name': tool.name,
                    'tool_type': tool.tool_type,
                    'config': tool.config,
                    'agent_id': tool.agent_id
                })
        
        # Create a single node representing this agent with its tools
        agent_node = {
            'id': agent_id,
            'type': 'agent',
            'reference': {
                'id': agent_db.id,
                'name': agent_db.name,
                'prompt': agent_db.prompt,
                'model_id': agent_db.model_id,
                'description': agent_db.description,
                'tools': agent_tools
            }
        }
        
        # Initialize workflow context with the agent as a single node
        workflow_context = {
            'id': agent_id,
            'name': agent_db.name,
            'description': agent_db.description,
            'model_id': agent_db.model_id,
            'nodes': {str(agent_id): agent_node},
            'edges': [],
            'conversation_history': [],
            'last_edited': None
        }
        
        return workflow_context
    
    @classmethod
    def set_active_workflow(cls, workflow_id: uuid.UUID, db_session) -> Dict[str, Any]:
        """
        Initialize a workflow instance and store it in the session.
        
        Args:
            workflow_id: ID of the workflow to instantiate
            db_session: SQLAlchemy database session
            
        Returns:
            Dict containing the initialized workflow data
        """
        # Load workflow data from database
        workflow_context = cls.load_workflow(workflow_id, db_session)
        #log workflow context formatted json 2 space indent
        print("WORKFLOW CONTEXT", json.dumps(workflow_context, indent=2,default=str))
        # Create agent instances for all agent nodes
        agents = cls.create_nodes(workflow_context)
        workflow_context['agents'] = agents
        
        # Create an orchestrator agent that manages the workflow
        orchestrator = cls._create_orchestrator(workflow_context)
        workflow_context['orchestrator'] = orchestrator
        
        # Generate a unique session ID and store in the global dictionary
        session_id = str(workflow_context['id'])
        cls._workflow_contexts[session_id] = workflow_context
        
        # Store the current timestamp for this workflow
        cls._workflow_edit_timestamps[workflow_id] = workflow_context['last_edited'] or 0
        
        return workflow_context
        
    @classmethod
    def set_active_agent(cls, agent_id: uuid.UUID, db_session) -> Dict[str, Any]:
        """
        Initialize a single agent as the orchestrator and store it in the session.
        
        Args:
            agent_id: ID of the agent to use as orchestrator
            db_session: SQLAlchemy database session
            
        Returns:
            Dict containing the initialized agent data
        """
        # Load the agent from the database
        agent_db = db_session.query(Agent).get(agent_id)
        if not agent_db:
            raise ValueError(f"Agent with ID {agent_id} not found")
        
        # Initialize workflow context with minimal information
        workflow_context = {
            'id': agent_id,
            'name': agent_db.name,
            'description': agent_db.description,
            'nodes': {},
            'edges': [],
            'conversation_history': [],
            'last_edited': None
        }
        
        # Create the agent instance
        agent_data = {
            'reference': {
                'id': agent_db.id,
                'name': agent_db.name,
                'prompt': agent_db.prompt
            }
        }
        #log agent data formatted json 2 space indent
        print("AGENT DATA", json.dumps(agent_data, indent=2, default=str))
        agent = cls.create_agent(agent_data, db_session)
        
        # Use the agent directly as the orchestrator
        workflow_context['orchestrator'] = agent
        workflow_context['agents'] = [agent]
        
        # Generate a unique session ID and store in the global dictionary
        session_id = str(agent_id)
        cls._workflow_contexts[session_id] = workflow_context
        
        return workflow_context
    
    @classmethod
    def create_nodes(cls, workflow_context, log_queue):
        workflow_name = workflow_context.get('name', 'Unknown Workflow')
        print(f"Creating nodes for workflow: {workflow_name}")
        print(f"Workflow has {len(workflow_context['nodes'])} nodes")
        print(f"Workflow context keys: {list(workflow_context.keys())}")
        
        agents = []
        tools = []
        for node_id, node_data in workflow_context['nodes'].items():
            node_type = node_data.get('type', 'unknown')
            node_name = node_data.get('reference', {}).get('name', f'Node {node_id}')
            print(f"Processing node: {node_name} (type: {node_type})")
            print(f"Node data keys: {list(node_data.keys())}")
            print(f"Node reference: {node_data.get('reference', {})}")
            
            if node_data['type'] == 'agent':
                agent = cls.create_agent(node_data, log_queue)
                if agent:
                    print(f"Successfully created agent: {node_name}")
                    print(f"Agent has {len(agent.tools) if hasattr(agent, 'tools') else 0} tools")
                    agents.append(agent)
                else:
                    print(f"WARNING: Failed to create agent: {node_name}")
            elif node_data['type'] == 'tool':
                tool_instance = cls.create_tool(node_data, log_queue)
                if tool_instance:
                    print(f"Successfully created tool: {node_name}")
                    tools.append(tool_instance)
                else:
                    print(f"WARNING: Failed to create tool: {node_name}")
        
        print(f"Workflow {workflow_name} final counts - Agents: {len(agents)}, Tools: {len(tools)}")
        workflow_context['tools'] = tools
        return agents

    @classmethod
    def create_tool(cls, tool_data, log_queue):
        """
        Create a Strands tool instance from a tool node.
        
        Args:
            tool_data: Dictionary containing tool configuration
            log_queue: Queue for logging messages
            
        Returns:
            Strands tool instance
        """
        if not tool_data.get('reference'):
            return None
            
        tool_ref = tool_data['reference']
        
        # Create tool instance based on type using reference data
        tool_instance = cls._create_tool_instance_from_data(tool_ref, log_queue)
        return tool_instance

    @classmethod
    def create_agent(cls, agent_data, log_queue):
        """
        Create a Strands agent with its tools.
        
        Args:
            agent_data: Dictionary containing agent configuration
            log_queue: Queue for logging messages
            
        Returns:
            StrandsAgent instance
        """
        if not agent_data.get('reference'):
            print(f"ERROR: No reference data found for agent")
            return None
            
        agent_ref = agent_data['reference']
        agent_name = agent_ref.get('name', 'Unknown Agent')
        print(f"Creating agent: {agent_name}")
        print(f"Agent reference keys: {list(agent_ref.keys())}")
        
        # Create tools from reference data
        agent_tools = []
        tools_data = agent_ref.get('tools', [])
        print(f"Agent {agent_name} has {len(tools_data)} tools configured")
        print(f"Tools data: {tools_data}")
        
        for i, tool_data in enumerate(tools_data):
            tool_name = tool_data.get('name', 'Unknown')
            tool_type = tool_data.get('tool_type', 'Unknown')
            print(f"Processing tool {i+1}/{len(tools_data)} for agent {agent_name}: {tool_name} (type: {tool_type})")
            print(f"Tool data: {tool_data}")
            
            try:
                tool_instance = cls._create_tool_instance_from_data(tool_data, log_queue)
                if tool_instance:
                    print(f"Successfully created tool instance for {tool_name}, adding {len(tool_instance)} tools")
                    if isinstance(tool_instance, list):
                        for j, tool in enumerate(tool_instance):
                            tool_func_name = getattr(tool, '__name__', f'tool_{j}')
                            print(f"  - Tool {j}: {tool_func_name}")
                    agent_tools += tool_instance
                else:
                    print(f"WARNING: Failed to create tool instance for {tool_name} - returned None")
            except Exception as e:
                print(f"ERROR: Exception creating tool instance for {tool_name}: {str(e)}")
                import traceback
                traceback.print_exc()
        
        print(f"Agent {agent_name} final tool count: {len(agent_tools)}")
        if agent_tools:
            print(f"Final tools list:")
            for i, tool in enumerate(agent_tools):
                tool_name = getattr(tool, '__name__', f'tool_{i}')
                print(f"  - {i}: {tool_name}")
        
        # Create a Strands agent instance
        model_arg = agent_ref.get('model_id')
        print(f"Agent {agent_name} using model: {model_arg}")
        
        # Use cross-region profile if available
        if model_arg:
            try:
                from bedrock_models import get_model_with_cross_region_profile
                model_arg = get_model_with_cross_region_profile(model_arg)
                print(f"Agent {agent_name} cross-region model: {model_arg}")
            except Exception as e:
                print(f"WARNING: Failed to get cross-region model: {str(e)}")
        
        try:
            strands_agent = StrandsAgent(
                model=model_arg,
                system_prompt=agent_ref['prompt'],
                tools=agent_tools
            )
            strands_agent.__agent_name = agent_ref['name']
            strands_agent.__agent_desctription = agent_ref.get('description', '')
            print(f"Successfully created Strands agent: {agent_name}")
            print(f"Strands agent has {len(strands_agent.tools) if hasattr(strands_agent, 'tools') else 0} tools")
            return strands_agent
        except Exception as e:
            print(f"ERROR: Failed to create Strands agent {agent_name}: {str(e)}")
            import traceback
            traceback.print_exc()
            return None
        
    @classmethod
    def _create_tool_instance_from_data(cls, tool_data: Dict[str, Any], log_queue):
        """
        Create a Strands tool instance from tool data.
        
        Args:
            tool_data: Dictionary containing tool data
            log_queue: Queue for logging messages
            
        Returns:
            A Strands tool instance (BuiltinTool, MCPTool, or StrandsAgentTool)
        """
        tool_name = tool_data.get('name', 'Unknown')
        tool_type = tool_data.get('tool_type', 'Unknown')
        print(f"Creating tool instance for: {tool_name} (type: {tool_type})")
        print(f"Tool data keys: {list(tool_data.keys())}")
        print(f"Full tool data: {tool_data}")
        
        # Parse tool configuration if available
        try:
            from mcp_helpers import parse_config
            config = parse_config(tool_data.get('config'))
            print(f"Parsed config for {tool_name}: {config}")
        except Exception as e:
            print(f"ERROR: Failed to parse config for {tool_name}: {str(e)}")
            config = {}
        
        # Create the appropriate tool instance based on type
        if tool_data['tool_type'] == 'builtin':
            print(f"Processing builtin tool: {tool_name}")
            
            # Map tool name to the appropriate strands_tools module
            tool_mapping = {
                'file_read': file_read,
                'file_write': file_write,
                'editor': editor,
                'shell': shell,
                'http_request': http_request,
                'python_repl': python_repl,
                'calculator': calculator,
                'use_aws': use_aws,
                'retrieve': retrieve,
                'nova_reels': nova_reels,
                'memory': memory,
                'environment': environment,
                'generate_image': generate_image,
                'image_reader': image_reader,
                'journal': journal,
                'think': think_tool,
                'load_tool': load_tool,
                'swarm': swarm,
                'current_time': current_time,
                'sleep': sleep,
                'agent_graph': agent_graph,
                'cron': cron,
                'slack': slack,
                'speak': speak,
                'stop': stop,
                #'use_llm': use_llm_tool,
                'workflow': workflow,
                'batch': batch
            }
            
            print(f"Available builtin tools: {list(tool_mapping.keys())}")
            tool_name_lower = tool_name.lower()
            print(f"Looking for tool: '{tool_name_lower}'")
            
            # Get the tool from the mapping
            tool_module = tool_mapping.get(tool_name_lower)
            if tool_module:
                print(f"Found builtin tool module: {tool_module}")
                print(f"Tool module type: {type(tool_module)}")
                print(f"Tool module name: {getattr(tool_module, '__name__', 'Unknown')}")
                return [tool_module]
            else:
                print(f"ERROR: Builtin tool '{tool_name_lower}' not found in mapping")
                return None
            
        elif tool_data['tool_type'] == 'mcp':
            print(f"Processing MCP tool: {tool_name}")
            
            try:
                # Create an MCP client based on the config
                from mcp_helpers import locate_config
                
                command, args, env, _ = locate_config(config)
                print(f"Located MCP config - command: {command}, args: {args}, env: {env}")
                
                # Get disabled_tools from root config
                disabled_tools = config.get('disabled_tools', [])
                print(f"Disabled tools: {disabled_tools}")
                
                if not command:
                    print(f"ERROR: No command found in config for {tool_name}")
                    return None

                print(f"Creating MCP client for {tool_name}")
                
                # Create MCP client using stdio transport
                mcp_client = MCPClient(lambda: stdio_client(
                    StdioServerParameters(
                        command=command,
                        args=args,
                        env=env
                    )
                ))
                
                print(f"Starting MCP client for {tool_name}")
                # Get tools from the MCP server
                mcp_client.start()
                
                print(f"Listing tools from MCP server for {tool_name}")
                all_tools = mcp_client.list_tools_sync()
                print(f"Found {len(all_tools) if all_tools else 0} tools from MCP server")
                
                if all_tools:
                    for i, tool in enumerate(all_tools):
                        tool_name_attr = getattr(tool, 'name', getattr(tool.mcp_tool, 'name', f'tool_{i}'))
                        print(f"MCP Tool {i}: {tool_name_attr}")

                # Filter out disabled tools
                if disabled_tools and all_tools:
                    print(f"Filtering out disabled tools: {disabled_tools}")
                    filtered_tools = [tool for tool in all_tools if tool.mcp_tool.name not in disabled_tools]
                    print(f"After filtering: {len(filtered_tools)} tools remaining")
                    return filtered_tools
                
                print(f"Returning {len(all_tools) if all_tools else 0} MCP tools")
                return all_tools
                
            except Exception as e:
                print(f"ERROR: Failed to initialize MCP client for {tool_name}: {str(e)}")
                import traceback
                traceback.print_exc()
                return None
            
        elif tool_data['tool_type'] == 'agent' and tool_data.get('agent_id'):
            print(f"Processing agent tool: {tool_name}")
            
            # For agent tools, create a function that calls the agent
            def agent_tool_function(message):
                # This would need to be implemented to call the agent
                # For now, return a placeholder
                return f"Agent tool {tool_data['name']} called with: {message}"
            
            agent_tool_function.__name__ = tool_data['name']
            agent_tool_function.__doc__ = f"Tool that calls agent {tool_data['name']}"
            print(f"Created agent tool function: {agent_tool_function.__name__}")
            return [agent_tool_function]
        
        else:
            print(f"ERROR: Unknown tool type '{tool_type}' for tool '{tool_name}'")
            return None
    
    @classmethod
    def _create_tool_instance(cls, tool: Tool, log_queue, db_session=None):
        """
        Create a Strands tool instance based on its type.
        
        Args:
            tool: Tool model instance from database
            log_queue: Queue for logging messages
            db_session: SQLAlchemy database session (optional)
            
        Returns:
            A Strands tool instance (BuiltinTool, MCPTool, or StrandsAgentTool)
        """
        # Convert Tool model to dict and use the new method
        tool_data = {
            'id': tool.id,
            'name': tool.name,
            'tool_type': tool.tool_type,
            'config': tool.config,
            'agent_id': tool.agent_id
        }
        return cls._create_tool_instance_from_data(tool_data, log_queue)

    @classmethod
    def clear_active_workflow(cls, session_id: str = None) -> None:
        """
        Clear the active workflow from the session.
        
        Args:
            session_id: The session ID to clear
        """
        if session_id and session_id in cls._workflow_contexts:
            # Remove from global dictionary
            del cls._workflow_contexts[session_id]
    
    @classmethod
    def clear_workflow_sessions(cls, workflow_id: uuid.UUID) -> None:
        """
        Clear all sessions using a specific workflow.
        
        Args:
            workflow_id: ID of the workflow to clear sessions for
        """
        # Convert workflow_id to string for comparison with session_id
        workflow_id_str = str(workflow_id)
        
        # Remove from global dictionary
        if workflow_id_str in cls._workflow_contexts:
            del cls._workflow_contexts[workflow_id_str]
        
        # Update edit timestamp
        cls._workflow_edit_timestamps[workflow_id] = 0
    
    @classmethod
    async def deliver_message(cls, message: str, session_id: str = None, db_session = None):
        """
        Deliver a message from the chat to the active workflow.
        
        Args:
            message: The message from the user
            session_id: The session ID to use
            db_session: SQLAlchemy database session
            
        Returns:
            Dict containing the response from the workflow
            
        Raises:
            ValueError: If no workflow is active or if workflow was edited
        """
        # Find the active workflow context
        active_workflow = None
        active_session_id = None
        
        # If session_id is provided, use it
        if session_id and session_id in cls._workflow_contexts:
            active_workflow = cls._workflow_contexts[session_id]
            active_session_id = session_id
        # Otherwise, try to find any active workflow
        elif len(cls._workflow_contexts) > 0:
            active_session_id = next(iter(cls._workflow_contexts.keys()))
            active_workflow = cls._workflow_contexts[active_session_id]
        
        if not active_workflow:
            raise ValueError("No active workflow to deliver message to")
        
        workflow = active_workflow
        workflow_id = workflow['id']
        
        # Check if workflow was edited since session was created
        if workflow_id in cls._workflow_edit_timestamps and db_session:
            # Get current workflow from database to check last_edited
            current_workflow = db_session.query(Workflow).get(workflow_id)
            if current_workflow and hasattr(current_workflow, 'last_edited') and current_workflow.last_edited:
                if cls._workflow_edit_timestamps[workflow_id] < current_workflow.last_edited:
                    raise ValueError("This workflow has been edited since the session was created")
        
        # Add message to conversation history
        workflow['conversation_history'].append({
            'role': 'user',
            'content': message
        })
        
        # Use the orchestrator to process the message
        orchestrator = workflow.get('orchestrator')
        response_content = ""
        async for event in orchestrator.stream_async(message):
            if "data" in event:
                response_content += event["data"]
            
            yield "data: " + json.dumps(event, default=str) + "\n"
            

        response = {
            'content': str(response_content)
        }
        
        # Add response to conversation history
        workflow['conversation_history'].append({
            'role': 'assistant',
            'content': response['content']
        })
        
    

        
    @classmethod
    def _create_orchestrator(cls, workflow_context, log_queue):
        """
        Create an orchestrator agent that manages the workflow execution.
        
        Args:
            workflow_context: Dictionary containing workflow data
            log_queue: Queue for logging messages
            
        Returns:
            StrandsAgent instance configured as an orchestrator
        """
        # Create agent tools for each agent in the workflow
        all_tools = []
        
        # Add agent tools
        for agent in workflow_context['agents']:
            #instantiate StrandsAgent class loading the right agent spec
            def capture(__captured = agent):
                def f(task: str):
                    return __captured(task)
                return f
            agent_wrapper = capture()
            #name must be [a-zA-Z0-9_-]+ replace anything else with _ using a regex
            agent_wrapper.__name__ = re.sub(r'[^a-zA-Z0-9_-]', '_', agent.__agent_name)
            agent_wrapper.__doc__ = agent.__agent_desctription or f" Execute the agent called {agent.__agent_name} " 
            
            agent_wrapper = tool(agent_wrapper)

            all_tools.append(agent_wrapper)
        
        # Add direct tool invocations from workflow
        if 'tools' in workflow_context and workflow_context['tools']:
            for tool_list in workflow_context['tools']:
                if tool_list:
                    for tool_instance in tool_list:
                        # Add each tool to the orchestrator's tools
                        all_tools.append(tool_instance)
        
        # Generate a system prompt describing the workflow graph
        system_prompt = cls._generate_workflow_prompt(workflow_context)
       
        
        # Create the orchestrator agent with the workflow's model if specified
        model_id = workflow_context.get('model_id')
        
        # Use cross-region profile if available
        if model_id:
            from bedrock_models import get_model_with_cross_region_profile
            model_id = get_model_with_cross_region_profile(model_id)
            
        orchestrator = StrandsAgent(
            model=model_id,
            system_prompt=system_prompt,
            tools=all_tools
        )
        
        return orchestrator
        
    @classmethod
    def _recover_json(cls, malformed_json: str) -> Dict[str, Any]:
        """
        Attempt to recover a dictionary from malformed JSON.
        
        This method uses several strategies to extract key-value pairs from malformed JSON:
        1. Fix common syntax errors (missing quotes, trailing commas, etc.)
        2. Use regex to extract key-value pairs
        3. Fall back to extracting simple key-value patterns
        
        Args:
            malformed_json: String containing potentially malformed JSON
            
        Returns:
            Dictionary with recovered key-value pairs
        """
        if not malformed_json:
            return {}
            
        # Strategy 1: Fix common syntax errors
        fixed_json = malformed_json.strip()
        
        # Fix trailing commas in objects and arrays
        fixed_json = re.sub(r',\s*}', '}', fixed_json)
        fixed_json = re.sub(r',\s*]', ']', fixed_json)
        
        # Fix missing quotes around keys
        fixed_json = re.sub(r'(\{|\,)\s*([a-zA-Z0-9_]+)\s*:', r'\1"\2":', fixed_json)
        
        if not fixed_json.startswith('{') and not fixed_json.startswith("["): 
            fixed_json = '{' + fixed_json + '}'

        # Try to parse the fixed JSON
        try:
            return json.loads(fixed_json)
        except:
            pass
            
        # Strategy 2: Use regex to extract key-value pairs
        try:
            result = {}
            # Match "key": value patterns (string values)
            string_pattern = r'"([^"]+)"\s*:\s*"([^"]*)"'
            for match in re.finditer(string_pattern, malformed_json):
                key, value = match.groups()
                result[key] = value
                
            # Match "key": value patterns (numeric values)
            num_pattern = r'"([^"]+)"\s*:\s*(-?\d+(?:\.\d+)?)'
            for match in re.finditer(num_pattern, malformed_json):
                key, value = match.groups()
                try:
                    # Convert to int or float as appropriate
                    if '.' in value:
                        result[key] = float(value)
                    else:
                        result[key] = int(value)
                except:
                    result[key] = value
                    
            # Match "key": true/false patterns (boolean values)
            bool_pattern = r'"([^"]+)"\s*:\s*(true|false)'
            for match in re.finditer(bool_pattern, malformed_json):
                key, value = match.groups()
                result[key] = (value.lower() == 'true')
                
            # If we found any key-value pairs, return them
            if result:
                return result
        except:
            pass
            
        # Strategy 3: Last resort - try to extract any key-value like patterns
        try:
            result = {}
            # Look for patterns like key=value or key: value
            pattern = r'([a-zA-Z0-9_]+)[=:]\s*([a-zA-Z0-9_./\\-]+)'
            for match in re.finditer(pattern, malformed_json):
                key, value = match.groups()
                # Try to convert value to appropriate type
                if value.lower() == 'true':
                    result[key] = True
                elif value.lower() == 'false':
                    result[key] = False
                elif value.isdigit():
                    result[key] = int(value)
                elif re.match(r'^-?\d+\.\d+$', value):
                    result[key] = float(value)
                else:
                    result[key] = value
            return result
        except:
            # If all strategies fail, return empty dict
            return {}
    
    @classmethod
    def _generate_workflow_prompt(cls, workflow_context):
        """
        Generate a system prompt describing the workflow graph.
        
        Args:
            workflow_context: Dictionary containing workflow data
            
        Returns:
            String containing the system prompt
        """
        workflow = workflow_context
        nodes = workflow['nodes']
        edges = workflow['edges']
        
        # Start building the prompt
        prompt = f"# Workflow: {workflow['name']}\n\n"
        prompt += f"{workflow['description']}\n\n"
        prompt += "## Your Role\n"
        prompt += "You are the Workflow Orchestrator responsible for managing the execution of this workflow. "
        prompt += "You receive user messages and route them through the workflow according to the graph structure below.\n\n"
        
        # Add graph structure description
        prompt += "## Workflow Graph Structure\n"
        
        # List all nodes (excluding input/output nodes)
        prompt += "### Nodes:\n"
        for node_id, node in nodes.items():
            if node['type'] not in ['input', 'output']:
                node_name = node.get('reference', {}).get('name', f"Node {node_id}")
                node_type = node['type']
                prompt += f"- {node_name} (ID: {node_id}, Type: {node_type})\n"
        
        # List all connections
        prompt += "\n### Edges:\n"
        for edge in edges:
            source_id = edge['source']
            target_id = edge['target']
            
            # Skip edges connected to input/output nodes

                
            source_name = nodes.get(source_id, {}).get('reference', {}).get('name', f"Node {source_id}")
            target_name = nodes.get(target_id, {}).get('reference', {}).get('name', f"Node {target_id}")
            if nodes.get(source_id, {}).get('type') == 'input':
                source_name = "the initial input"
            if nodes.get(target_id, {}).get('type') == 'output':
                target_name = "the user as final response"
            

            prompt += f"- You can from {source_name} send the result to the {target_name}\n"
        
        # Add instructions for handling messages
        prompt += "\n## Instructions\n"
        prompt += "1. When you receive a user message, identify the appropriate starting point in the workflow.\n"
        prompt += "2. Route the message through the workflow according to the graph structure.\n"
        prompt += "3. Each agent or tool in the workflow will process the message and produce a response.\n"
        prompt += "4. Follow the graph edges to determine the next node (agent or tool) to invoke.\n"
        prompt += "5. For agent nodes, use the corresponding agent tool to process the message.\n"
        prompt += "6. For tool nodes, use the corresponding tool directly to process the message.\n"
        prompt += "7. Return the final response to the user.\n"
        
        return prompt
