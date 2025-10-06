import { EventBridgeClient, PutEventsCommand } from '@aws-sdk/client-eventbridge';
import { APIGatewayProxyEvent, APIGatewayProxyResult } from 'aws-lambda';

// Initialize AWS clients
const eventBridgeClient = new EventBridgeClient({});

const EVENT_BUS_NAME = process.env.EVENT_BUS_NAME!;

interface UserRequest {
  text: string;
  invocationId: string;
}

interface AgentInvokedEvent {
  invocationId: string;
  text: string;
  timestamp: string;
}

/**
 * Lambda handler for submitting user research queries
 * Expects POST /query with body: { text: string, invocationId: string }
 */
export const handler = async (event: APIGatewayProxyEvent): Promise<APIGatewayProxyResult> => {
  console.log('Received user request:', JSON.stringify(event, null, 2));
  
  const headers = {
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Headers': 'Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token',
    'Access-Control-Allow-Methods': 'OPTIONS,POST',
    'Content-Type': 'application/json'
  };

  try {
    // Handle CORS preflight
    if (event.httpMethod === 'OPTIONS') {
      return {
        statusCode: 200,
        headers,
        body: JSON.stringify({ message: 'CORS preflight successful' })
      };
    }

    // Parse request body
    let requestBody: UserRequest;
    try {
      requestBody = JSON.parse(event.body || '{}') as UserRequest;
    } catch (parseError) {
      return {
        statusCode: 400,
        headers,
        body: JSON.stringify({ 
          error: 'Invalid JSON in request body' 
        })
      };
    }

    const { text, invocationId } = requestBody;

    if (!text || text.trim().length === 0) {
      return {
        statusCode: 400,
        headers,
        body: JSON.stringify({ 
          error: 'Text field is required and cannot be empty' 
        })
      };
    }

    if (!invocationId || invocationId.trim().length === 0) {
      return {
        statusCode: 400,
        headers,
        body: JSON.stringify({ 
          error: 'InvocationId is required' 
        })
      };
    }

    // Create AgentInvoked event
    const agentInvokedEvent: AgentInvokedEvent = {
      invocationId,
      text,
      timestamp: new Date().toISOString()
    };

    // Emit AgentInvoked event to EventBridge
    await eventBridgeClient.send(new PutEventsCommand({
      Entries: [{
        Source: 'user-interface',
        DetailType: 'AgentInvoked',
        Detail: JSON.stringify(agentInvokedEvent),
        EventBusName: EVENT_BUS_NAME,
      }]
    }));

    console.log('User request submitted:', { invocationId, text });

    return {
      statusCode: 200,
      headers,
      body: JSON.stringify({
        success: true,
        invocationId,
        message: 'Request submitted successfully'
      })
    };

  } catch (error) {
    console.error('Error submitting user request:', error);
    
    return {
      statusCode: 500,
      headers,
      body: JSON.stringify({
        error: 'Internal server error',
        message: (error as Error).message
      })
    };
  }
};