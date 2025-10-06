import { EventBridgeEvent, Context } from 'aws-lambda';
import { S3Client, GetObjectCommand } from '@aws-sdk/client-s3';
import { getSignedUrl } from '@aws-sdk/s3-request-presigner';

// Initialize AWS clients
const s3Client = new S3Client({});

interface AgentExecutedEventDetail {
  invocationId: string;
  summary: string;
  s3Uri?: string;
}

interface ResearchResponse {
  invocationId: string;
  summary: string;
  s3Uri?: string;
  presignedUrl?: string;
  timestamp: string;
}

// EventBridge event structure for AgentExecuted
type AgentExecutedEvent = EventBridgeEvent<'AgentExecuted', AgentExecutedEventDetail>;

/**
 * Lambda handler for processing AgentExecuted events
 * Receives events from EventBridge containing agent completion data
 */
export const handler = async (event: AgentExecutedEvent, context: Context): Promise<void> => {
  console.log('Received AgentExecuted event:', JSON.stringify(event, null, 2));
  
  try {
    const { detail } = event;
    const { invocationId, summary, s3Uri } = detail;

    if (!invocationId || !summary) {
      throw new Error('Missing required fields: invocationId and summary');
    }

    await processAgentResponse({
      invocationId,
      summary,
      s3Uri
    });

    console.log('Successfully processed agent response');

  } catch (error) {
    console.error('Error processing AgentExecuted event:', error);
    throw error; // Re-throw to trigger Lambda error handling
  }
};

async function processAgentResponse(params: {
  invocationId: string;
  summary: string;
  s3Uri?: string;
}): Promise<void> {
  const { invocationId, summary, s3Uri } = params;

  let presignedUrl: string | undefined;
  if (s3Uri) {
    presignedUrl = await generatePresignedUrl(s3Uri);
  }

  const researchResponse: ResearchResponse = {
    invocationId,
    summary,
    s3Uri,
    presignedUrl,
    timestamp: new Date().toISOString(),
  };

  await publishToAppSyncEvents(researchResponse);
}

async function publishToAppSyncEvents(researchResponse: ResearchResponse): Promise<void> {
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
        channel: `/agent/${researchResponse.invocationId}`,
        events: [JSON.stringify(researchResponse)]
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
  
  if (s3Uri.includes('.s3.') && s3Uri.includes('.amazonaws.com')) {
    const url = new URL(s3Uri);
    const bucket = url.hostname.split('.')[0];
    const key = url.pathname.substring(1);
    return { bucket, key };
  }
  
  return null;
}