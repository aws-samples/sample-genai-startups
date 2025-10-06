import { DynamoDBClient } from '@aws-sdk/client-dynamodb';
import { DynamoDBDocumentClient, GetCommand, UpdateCommand } from '@aws-sdk/lib-dynamodb';
import { EventBridgeClient, PutEventsCommand } from '@aws-sdk/client-eventbridge';
import { APIGatewayProxyEvent, APIGatewayProxyResult } from 'aws-lambda';

// Initialize AWS clients
const dynamoClient = new DynamoDBClient({});
const docClient = DynamoDBDocumentClient.from(dynamoClient);
const eventBridgeClient = new EventBridgeClient({});

const TABLE_NAME = process.env.TABLE_NAME!;
const EVENT_BUS_NAME = process.env.EVENT_BUS_NAME!;

interface ReviewSubmissionRequest {
  decision: 'approved' | 'rejected';
  comments?: string;
  invocationId: string;
}

interface ReviewRecord {
  id: string;
  agentInvocationId: string;
  toolName: string;
  query: string;
  summary: string;
  s3uri?: string;
  decision: 'pending' | 'approved' | 'rejected';
  comments?: string;
  createdAt: string;
  updatedAt?: string;
}

interface ToolExecutedEvent {
  invocationId: string;
  agentInvocationId: string;
  toolName: string;
  result: {
    decision: 'approved' | 'rejected';
    comments?: string;
    timestamp: string;
  };
}

/**
 * Lambda handler for submitting human review results
 * Expects POST /reviews with body: { invocationId: string, decision: 'approved'|'rejected', comments?: string }
 */
export const handler = async (event: APIGatewayProxyEvent): Promise<APIGatewayProxyResult> => {
  console.log('Received submit review event:', JSON.stringify(event, null, 2));
  
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
    let requestBody: ReviewSubmissionRequest;
    try {
      requestBody = JSON.parse(event.body || '{}') as ReviewSubmissionRequest;
    } catch (parseError) {
      return {
        statusCode: 400,
        headers,
        body: JSON.stringify({ 
          error: 'Invalid JSON in request body' 
        })
      };
    }

    const { decision, comments, invocationId: reviewId } = requestBody;

    if (!reviewId) {
      return {
        statusCode: 400,
        headers,
        body: JSON.stringify({ 
          error: 'Missing invocationId in request body' 
        })
      };
    }

    // Validate decision
    if (!decision || !['approved', 'rejected'].includes(decision)) {
      return {
        statusCode: 400,
        headers,
        body: JSON.stringify({ 
          error: 'Decision must be either "approved" or "rejected"' 
        })
      };
    }

    // Get the existing review record
    const getResult = await docClient.send(new GetCommand({
      TableName: TABLE_NAME,
      Key: { id: reviewId }
    }));

    const existingReview = getResult.Item as ReviewRecord | undefined;
    
    if (!existingReview) {
      return {
        statusCode: 404,
        headers,
        body: JSON.stringify({ error: 'Review not found' })
      };
    }

    // Update the review record
    const updatedAt = new Date().toISOString();
    const updateResult = await docClient.send(new UpdateCommand({
      TableName: TABLE_NAME,
      Key: { id: reviewId },
      UpdateExpression: 'SET decision = :decision, updatedAt = :updatedAt' + 
                      (comments ? ', comments = :comments' : ''),
      ExpressionAttributeValues: {
        ':decision': decision,
        ':updatedAt': updatedAt,
        ...(comments && { ':comments': comments })
      },
      ReturnValues: 'ALL_NEW'
    }));

    const updatedReview = updateResult.Attributes as ReviewRecord;

    // Emit ToolExecuted event
    const toolExecutedEvent: ToolExecutedEvent = {
      invocationId: reviewId,
      agentInvocationId: existingReview.agentInvocationId,
      toolName: existingReview.toolName,
      result: { 
        decision, 
        comments,
        timestamp: updatedAt
      }
    };

    await eventBridgeClient.send(new PutEventsCommand({
      Entries: [{
        Source: 'human-reviewer',
        DetailType: 'ToolExecuted',
        Detail: JSON.stringify(toolExecutedEvent),
        EventBusName: EVENT_BUS_NAME,
      }]
    }));

    console.log('Review submitted:', { reviewId, decision, comments });

    return {
      statusCode: 200,
      headers,
      body: JSON.stringify({
        success: true,
        reviewId,
        decision,
        comments,
        updatedAt: updatedReview.updatedAt
      })
    };

  } catch (error) {
    console.error('Error submitting review:', error);
    
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