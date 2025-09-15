"""
Strands Solar Panel Support Agent with Langfuse Observability

This agent provides solar panel installation and maintenance support using:
- Strands framework for agent orchestration
- Langfuse for comprehensive observability and evaluation
- AWS services for data persistence and knowledge retrieval
"""

import os
import json
import base64
import uuid
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime, timezone

import boto3
from boto3.dynamodb.conditions import Key
from dotenv import load_dotenv

from strands import Agent, tool
from strands_tools import current_time, memory, use_agent
from langfuse import observe, get_client as get_langfuse_client

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Build Basic Auth header.
LANGFUSE_AUTH = base64.b64encode(
    f"{os.environ.get('LANGFUSE_PUBLIC_KEY')}:{os.environ.get('LANGFUSE_SECRET_KEY')}".encode()
).decode()
 
# Configure OpenTelemetry endpoint & headers
os.environ["OTEL_EXPORTER_OTLP_ENDPOINT"] = os.environ.get("LANGFUSE_HOST") + "/api/public/otel"
os.environ["OTEL_EXPORTER_OTLP_HEADERS"] = f"Authorization=Basic {LANGFUSE_AUTH}"

# Initialize AWS resources
dynamodb_resource = boto3.resource('dynamodb', region_name=os.getenv('AWS_REGION', 'us-east-1'))
dynamodb_table_name = os.getenv('DYNAMODB_TABLE')
dynamodb_pk = os.getenv('DYNAMODB_PK', 'customer_id')
dynamodb_sk = os.getenv('DYNAMODB_SK', 'ticket_id')

# Initialize Langfuse client
langfuse = get_langfuse_client()

@tool
@observe(name="open_support_ticket")
def open_ticket(customer_id: str, msg: str) -> dict:
    """
    Open a new support ticket for a customer.
    
    Args:
        customer_id (str): The unique identifier for the customer (use the customer ID from the conversation context)
        msg (str): The support request message/description
        
    Returns:
        str: Confirmation message with ticket ID
    """
    try:
        # If customer_id looks like a context marker, extract the actual ID
        if customer_id.startswith("[Customer ID:"):
            # Extract customer ID from context format: "[Customer ID: demo_customer_001] query..."
            import re
            match = re.search(r'\[Customer ID:\s*([^\]]+)\]', customer_id)
            if match:
                actual_customer_id = match.group(1).strip()
            else:
                actual_customer_id = customer_id
        else:
            actual_customer_id = customer_id
            
        ticket_id = str(uuid.uuid1())
        
        # Update current trace with customer context
        langfuse.update_current_trace(
            user_id=actual_customer_id,
            tags=["support_ticket", "creation"],
            metadata={
                "ticket_id": ticket_id,
                "action": "create_ticket",
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
        )
        
        item = {
            'ticket_id': ticket_id,
            'customer_id': actual_customer_id,
            'description': msg,
            'status': 'created',
            'created_at': datetime.now(timezone.utc).isoformat()
        }
        
        table = dynamodb_resource.Table(dynamodb_table_name)
        response = table.put_item(Item=item)
        
        # Score the ticket creation success
        langfuse.score_current_trace(
            name="ticket_creation_success",
            value=1.0,
            data_type="NUMERIC",
            comment="Ticket created successfully"
        )
        
        result = f"Thanks for contacting us, customer {actual_customer_id}! Your support case was generated with ID: {ticket_id}"
        
        #logger.info(f"Created ticket {ticket_id} for customer {actual_customer_id}")
        
        # Return proper ToolResult format
        return result
        
    except Exception as e:
        logger.error(f"Error creating ticket for customer {customer_id}: {str(e)}")
        
        # Score the failure
        langfuse.score_current_trace(
            name="ticket_creation_success",
            value=0.0,
            data_type="NUMERIC",
            comment=f"Ticket creation failed: {str(e)}"
        )
        
        error_text = f"Sorry, there was an error creating your support ticket. Please try again later. Error: {str(e)}"
        
        # Return proper ToolResult format for error
        return error_text

@tool
@observe(name="get_ticket_status")
def get_ticket_status(customer_id: str, ticket_id: Optional[str] = None) -> dict:
    """
    Retrieve the status of support tickets for a customer.
    
    Args:
        customer_id (str): The unique identifier for the customer (use the customer ID from the conversation context)
        ticket_id (str, optional): Specific ticket ID to query. If None, returns all tickets for customer
        
    Returns:
        str: Ticket status information formatted for user display
    """
    try:
        # If customer_id looks like a context marker, extract the actual ID
        if customer_id.startswith("[Customer ID:"):
            # Extract customer ID from context format: "[Customer ID: demo_customer_001] query..."
            import re
            match = re.search(r'\[Customer ID:\s*([^\]]+)\]', customer_id)
            if match:
                actual_customer_id = match.group(1).strip()
            else:
                actual_customer_id = customer_id
        else:
            actual_customer_id = customer_id

          
        # Update current trace with customer context
        langfuse.update_current_trace(
            user_id=actual_customer_id,
            tags=["support_ticket", "status_check"],
            metadata={
                "action": "get_ticket_status",
                "ticket_id": ticket_id,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
        )
        
        table = dynamodb_resource.Table(dynamodb_table_name)
        
        # Create query expression
        if ticket_id:
            key_expression = Key(dynamodb_pk).eq(actual_customer_id) & Key(dynamodb_sk).begins_with(ticket_id)
        else:
            key_expression = Key(dynamodb_pk).eq(actual_customer_id)

        query_data = table.query(KeyConditionExpression=key_expression)
        tickets = query_data.get('Items', [])
        
        if not tickets:
            result = f"No tickets found for customer {actual_customer_id}"
            if ticket_id:
                result += f" with ticket ID {ticket_id}"
        else:
            # Format ticket information for user display
            ticket_info = []
            for ticket in tickets:
                info = f"Ticket ID: {ticket['ticket_id']}, Status: {ticket['status']}"
                if 'created_at' in ticket:
                    info += f", Created: {ticket['created_at']}"
                if 'description' in ticket:
                    info += f", Description: {ticket['description'][:100]}..."
                ticket_info.append(info)
            
            result = f"Found {len(tickets)} ticket(s) for customer {actual_customer_id}:\n" + "\n".join(ticket_info)
        
        # Score the query success
        langfuse.score_current_trace(
            name="ticket_query_success",
            value=1.0,
            data_type="NUMERIC",
            comment=f"Successfully retrieved {len(tickets)} tickets"
        )
        
        #logger.info(f"Retrieved {len(tickets)} tickets for customer {actual_customer_id}")
        
        
        return result
        
    except Exception as e:
        logger.error(f"Error retrieving tickets for customer {customer_id}: {str(e)}")
        
        # Score the failure
        langfuse.score_current_trace(
            name="ticket_query_success",
            value=0.0,
            data_type="NUMERIC",
            comment=f"Ticket query failed: {str(e)}"
        )
        
        error_text = f"Sorry, there was an error retrieving your ticket information. Please try again later. Error: {str(e)}"
        
        
        return error_text

# Define the main agent with comprehensive system prompt
@observe(name="solar_agent_main")
def create_solar_agent():
    """Create and configure the solar panel support agent with observability."""
    
    system_prompt = """
    You are a helpful solar panel support agent for a solar energy company. Your role is to:

    1. **Customer Support**: Help customers with support tickets, including creating new tickets and checking existing ticket status
    2. **Technical Knowledge**: Provide information about solar panel installation, maintenance, and troubleshooting using the knowledge base
    3. **Professional Service**: Maintain a friendly, professional tone while being informative and helpful

    **Available Tools:**
    - open_ticket: Create new support tickets for customer issues
    - get_ticket_status: Check the status of existing support tickets
    - search_solar_knowledge: Search the Bedrock Knowledge Base for solar panel information (custom wrapper)
    - current_time: Get current date and time information

    **IMPORTANT - Customer ID Handling:**
    - The customer ID is automatically provided in the system context when users interact with you
    - You have access to the customer's ID and should use it directly when calling tools
    - NEVER ask the customer for their customer ID - you already have it
    - When creating tickets or checking status, use the customer ID from the context immediately
    - If a user mentions their customer ID in their message, acknowledge it but know that you already have access to their ID

    **CRITICAL - Ticket Creation Rules:**
    - ONLY create support tickets when the customer explicitly asks you to create one
    - DO NOT automatically create tickets just because you cannot find information in the knowledge base
    - If you cannot find information, offer to create a ticket but wait for the customer to confirm
    - Use phrases like "Would you like me to create a support ticket?" or "I can create a support ticket if you'd like"
    - Only use the open_ticket tool when the customer clearly requests ticket creation

    **Tool Usage Guidelines:**
    - For technical questions about solar panels, use memory tool with action="retrieve" to get relevant information from Bedrock knowledge base
    - When customers explicitly request help or ask you to create a ticket, use open_ticket immediately
    - When customers ask about ticket status, use get_ticket_status to check their tickets
    - Always use the customer ID from context when calling these tools

    **Response Guidelines:**
    - Be direct and helpful - don't ask for information you already have
    - For support requests, only create tickets when explicitly asked
    - Provide clear, actionable information from the knowledge base
    - Be empathetic to customer concerns and provide helpful solutions
    - Always confirm actions taken (like ticket creation) with specific details
    - If you cannot find specific information, offer to create a ticket but don't do it automatically
    
    **Response Format:**
    - Be concise but comprehensive
    - Use bullet points for multiple items when appropriate
    - Always confirm actions taken (like ticket creation)
    - Provide next steps when relevant
    """

    # Initialize the agent with tools and observability
    agent = Agent(
        model=os.getenv('STRANDS_MODEL', 'us.anthropic.claude-3-7-sonnet-20250219-v1:0'),
        tools=[
            open_ticket,
            get_ticket_status,
            memory,
            current_time
        ],
        system_prompt=system_prompt

    )
    
    # Update trace with agent initialization info
    langfuse.update_current_trace(
        name="Solar Panel Support Agent",
        tags=["agent_initialization", "solar_support"],
        metadata={
            "agent_type": "solar_support",
            "model": os.getenv('STRANDS_MODEL', 'us.anthropic.claude-3-7-sonnet-20250219-v1:0'),
            "environment": os.getenv('STRANDS_ENVIRONMENT', 'development'),
            "tools_count": 4,
            "initialization_time": datetime.now(timezone.utc).isoformat()
        }
    )
    
    return agent

@observe(name="agent_interaction")
def handle_user_query(query: str, customer_id: Optional[str] = None, session_id: Optional[str] = None) -> str:
    """
    Handle a user query with the solar agent, including comprehensive observability.
    
    Args:
        query (str): The user's question or request
        customer_id (str, optional): Customer identifier for personalization
        session_id (str, optional): Session identifier for conversation tracking
        
    Returns:
        str: The agent's response
    """

    
    try:
        # Set up trace context
        langfuse.update_current_trace(
            name="Solar Agent Interaction",
            user_id=customer_id,
            session_id=session_id,
            input={"query": query, "customer_id": customer_id},
            tags=["user_interaction", "solar_agent"],
            metadata={
                "query_length": len(query),
                "has_customer_id": customer_id is not None,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
        )
        
        # Create the agent
        agent = create_solar_agent()
        
        # Prepare the query with customer context if available
        if customer_id:
            contextual_query = f"[Customer ID: {customer_id}] {query}"
        else:
            contextual_query = query
        
        # Process the query
        response = agent(contextual_query)
        
        
        # Update trace with response
        langfuse.update_current_trace(
            output={"response": response}
        )
        
        # Score the interaction
        langfuse.score_current_trace(
            name="interaction_completion",
            value=1.0,
            data_type="NUMERIC",
            comment="User interaction completed successfully"
        )
        
        #logger.info(f"Successfully processed query for customer {customer_id}")
        return response
        
    except Exception as e:
        logger.error(f"Error processing query: {str(e)}")
        
        # Score the failure
        langfuse.score_current_trace(
            name="interaction_completion",
            value=0.0,
            data_type="NUMERIC",
            comment=f"Interaction failed: {str(e)}"
        )
        
        return f"I apologize, but I encountered an error processing your request. Please try again or contact support directly. Error: {str(e)}"

# Interactive demo function
@observe(name="interactive_agent_demo")
def run_interactive_demo():
    """Run an interactive demonstration of the solar agent."""
    
    print("🌞 Interactive Solar Panel Support Agent")
    print("=" * 50)
    print("This is an interactive demo where you can chat with the agent.")
    print("The agent will use tools as needed and can have follow-up conversations.")
    print("Type 'quit' to exit the demo.")
    print("=" * 50)
    
    # Get customer ID
    customer_id = input("\n👤 Enter your customer ID (or press Enter for 'demo_customer_001'): ").strip()
    if not customer_id:
        customer_id = "demo_customer_001"
    
    session_id = f"interactive_session_{customer_id}"
    
    print(f"\n✅ Starting session for customer: {customer_id}")
    print("💬 You can now chat with the solar support agent!")
    print("-" * 50)
    
    while True:
        # Get user input
        user_query = input(f"\n🗣️  You: ").strip()
        
        if user_query.lower() in ['quit', 'exit', 'bye']:
            print("\n👋 Thank you for using Solar Panel Support! Goodbye!")
            break
        
        if not user_query:
            print("Please enter a question or type 'quit' to exit.")
            continue
        
        print(f"\n🤖 Agent: ", end="", flush=True)
        
        try:
            # Get agent response
            response = handle_user_query(
                query=user_query,
                customer_id=customer_id,
                session_id=session_id
            )
            
            
        except Exception as e:
            print(f"❌ Error: {str(e)}")
        
    
    # Flush Langfuse events
    langfuse.flush()
    print("\n📊 Session data has been sent to Langfuse dashboard.")

if __name__ == "__main__":
    run_interactive_demo()
