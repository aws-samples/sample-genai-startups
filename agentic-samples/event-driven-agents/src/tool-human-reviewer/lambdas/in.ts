import { EventBridgeEvent, Context } from 'aws-lambda';
import { DynamoDBClient } from '@aws-sdk/client-dynamodb';
import { DynamoDBDocumentClient, PutCommand, GetCommand, UpdateCommand } from '@aws-sdk/lib-dynamodb';
import { S3Client, GetObjectCommand } from '@aws-sdk/client-s3';
import { getSignedUrl } from '@aws-sdk/s3-request-presigner';

// Initialize AWS clients
const dynamoClient = new DynamoDBClient({});
const docClient = DynamoDBDocumentClient.from(dynamoClient);
const s3Client = new S3Client({});

interface ToolInvokedEventDetail {
  toolName: string;
  arguments: {
    originalQuery: string;
    summary: string;
    s3Uri?: string;
  };
  invocationId: string;
  agentInvocationId: string;
}

interface ReviewRequest {
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

// EventBridge event structure for ToolInvoked
type ToolInvokedEvent = EventBridgeEvent<'ToolInvoked', ToolInvokedEventDetail>;

/**
 * Lambda handler for processing human reviewer tool invocations
 * Receives events from EventBridge containing document summary, original query, and invocation ID
 */
export const handler = async (event: ToolInvokedEvent, context: Context): Promise<void> => {
  console.log('Received ToolInvoked event:', JSON.stringify(event, null, 2));
  
  try {
    const { detail } = event;
    const { arguments: args, invocationId, agentInvocationId, toolName } = detail;
    const { originalQuery, summary, s3Uri } = args;

    if (!summary || !originalQuery || !invocationId) {
      throw new Error('Missing required fields');
    }

    await processHumanReview({
      invocationId,
      agentInvocationId,
      toolName,
      query: originalQuery,
      summary,
      s3Uri
    });

    console.log('Successfully processed human review request');

  } catch (error) {
    console.error('Error processing ToolInvoked event:', error);
    // TODO: Publish error event back to EventBridge for error handling
    throw error; // Re-throw to trigger Lambda error handling
  }
};

async function processHumanReview(params: {
  invocationId: string;
  agentInvocationId: string;
  toolName: string;
  query: string;
  summary: string;
  s3Uri?: string;
}): Promise<void> {
  const { invocationId, agentInvocationId, toolName, query, summary, s3Uri } = params;

  let presignedUrl: string | undefined;
  if (s3Uri) {
    presignedUrl = await generatePresignedUrl(s3Uri);
  }

  const reviewRequest: ReviewRequest = {
    id: invocationId,
    agentInvocationId,
    toolName,
    query,
    summary,
    s3uri: s3Uri,
    decision: 'pending',
    createdAt: new Date().toISOString(),
  };

  await docClient.send(new PutCommand({
    TableName: process.env.TABLE_NAME!,
    Item: reviewRequest,
    ConditionExpression: 'attribute_not_exists(id)'
  }));

  await publishToAppSyncEvents({
    ...reviewRequest,
    presignedUrl
  });
}

async function publishToAppSyncEvents(reviewRequest: ReviewRequest & { presignedUrl?: string }): Promise<void> {
  try {
    const apiUrl = process.env.EVENTS_API_URL!;
    const url = new URL(apiUrl);
    const httpDomain = url.hostname;
    
    const response = await fetch(apiUrl, {
      method: 'POST',
      headers: {
        'x-api-key': process.env.EVENTS_API_KEY!,
        'host': httpDomain,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        channel: '/human-reviewer/requests',
        events: [JSON.stringify(reviewRequest)]
      })
    });

    if (!response.ok) {
      const errorText = await response.text().catch(() => 'Unknown error');
      throw new Error(`AppSync request failed: ${response.status} ${response.statusText} - ${errorText}`);
    }
    
    console.log('Successfully published to AppSync Events');
  } catch (error) {
    console.error('Error publishing to AppSync Events API:', error);
  }
}

async function generatePresignedUrl(s3Uri: string): Promise<string> {
  const s3UriParts = parseS3Url(s3Uri);
  if (!s3UriParts) {
    throw new Error(`Invalid S3 URL: ${s3Uri}`);
  }

  const { bucket, key } = s3UriParts;
  const command = new GetObjectCommand({ Bucket: bucket, Key: key });
  
  return await getSignedUrl(s3Client, command, {
    expiresIn: 24 * 60 * 60, // 24 hours
  });
}

function parseS3Url(s3Uri: string): { bucket: string; key: string } | null {
  if (s3Uri.startsWith('s3://')) {
    const parts = s3Uri.substring(5).split('/');
    if (parts.length < 2) return null;
    
    const bucket = parts[0];
    const key = parts.slice(1).join('/');
    return { bucket, key };
  }
  
  if (s3Uri.includes('.s3.') && s3Uri.includes('.amazonaws.com/')) {
    const url = new URL(s3Uri);
    const bucket = url.hostname.split('.')[0];
    const key = url.pathname.substring(1);
    return { bucket, key };
  }
  
  return null;
}
