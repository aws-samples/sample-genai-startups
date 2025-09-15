"""
Strands Solar Panel Support Agent with Arize Observability

This agent provides solar panel installation and maintenance support using:
- Strands framework for agent orchestration
- Arize for comprehensive observability and evaluation
- AWS services for data persistence and knowledge retrieval
"""

import os
import json
import base64
import uuid
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime, timezone
from opentelemetry import baggage,context
import boto3
from boto3.dynamodb.conditions import Key
from dotenv import load_dotenv

from strands import Agent, tool
from strands_tools import current_time, memory, use_agent




# Load environment variables
load_dotenv()

session_id = "session_01"
ctx = baggage.set_baggage("session.id", session_id) # Set the session.id in baggage
context.attach(ctx)


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


# Initialize AWS resources
dynamodb_resource = boto3.resource('dynamodb', region_name=os.getenv('AWS_REGION', 'us-east-1'))
dynamodb_table_name = os.getenv('DYNAMODB_TABLE')
dynamodb_pk = os.getenv('DYNAMODB_PK', 'customer_id')
dynamodb_sk = os.getenv('DYNAMODB_SK', 'ticket_id')


@tool
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
        
        
        item = {
            'ticket_id': ticket_id,
            'customer_id': actual_customer_id,
            'description': msg,
            'status': 'created',
            'created_at': datetime.now(timezone.utc).isoformat()
        }
        
        table = dynamodb_resource.Table(dynamodb_table_name)
        response = table.put_item(Item=item)
        

        result = f"Thanks for contacting us, customer {actual_customer_id}! Your support case was generated with ID: {ticket_id}"
        
        #logger.info(f"Created ticket {ticket_id} for customer {actual_customer_id}")
        
        # Return proper ToolResult format
        return result
        
    except Exception as e:
        logger.error(f"Error creating ticket for customer {customer_id}: {str(e)}")
        
        
        error_text = f"Sorry, there was an error creating your support ticket. Please try again later. Error: {str(e)}"
        
        # Return proper ToolResult format for error
        return error_text

@tool
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
        
        
        #logger.info(f"Retrieved {len(tickets)} tickets for customer {actual_customer_id}")
        
        
        return result
        
    except Exception as e:
        logger.error(f"Error retrieving tickets for customer {customer_id}: {str(e)}")
        
        
        error_text = f"Sorry, there was an error retrieving your ticket information. Please try again later. Error: {str(e)}"
        
        
        return error_text

# Define the main agent with comprehensive system prompt
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
    
    
    return agent


# Main entry point for Bedrock Agent Core
# Integrate with Bedrock AgentCore
from bedrock_agentcore.runtime import BedrockAgentCoreApp
app = BedrockAgentCoreApp()
agent = create_solar_agent()
@app.entrypoint
def agent_invocation(payload, context):
    """Handler for agent invocation"""
    user_message = payload.get("prompt", "No prompt found in input, please guide customer to create a json payload with prompt key")
    result = agent(user_message)

    return {"result": result.message}

if __name__ == "__main__":
    app.run()