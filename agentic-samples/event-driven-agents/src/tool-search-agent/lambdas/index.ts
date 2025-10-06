import { EventBridgeEvent, Context, Callback } from 'aws-lambda';
import { EventBridgeClient, PutEventsCommand } from '@aws-sdk/client-eventbridge';
import { SecretsManagerClient, GetSecretValueCommand } from '@aws-sdk/client-secrets-manager';
import { LinkupClient } from 'linkup-sdk';

// Initialize AWS clients
const eventBridge = new EventBridgeClient({});
const secretsManager = new SecretsManagerClient({ region: process.env.AWS_REGION || 'us-west-2' });

// LinkUp API configuration
let LINKUP_API_KEY: string | null = null;
const MAX_RESULTS = 10;
const SEARCH_API_SECRET_ARN = process.env.SEARCH_API_SECRET_ARN;

// Define types
interface SearchResult {
  title: string;
  url: string;
  description?: string;
}

interface ExtractedContent {
  title: string;
  content: string;
  url: string;
}

interface BraveSearchResponse {
  web: {
    results: Array<{
      title: string;
      url: string;
      description: string;
    }>;
  };
}

interface SearchAgentResult {
  query: string;
  summary: string;
  sources: Array<{
    title: string;
    url: string;
  }>;
}

interface EventDetail {
  invocationId: string;
  agentInvocationId: string;
  toolName: string;
  arguments: {
    query: string;
  };
}

/**
 * Get the API key from Secrets Manager
 */
async function getApiKey(): Promise<string> {
  if (LINKUP_API_KEY) {
    return LINKUP_API_KEY;
  }
  
  try {
    if (!SEARCH_API_SECRET_ARN) {
      throw new Error('SEARCH_API_SECRET_ARN environment variable is not set!');
    }
    
    console.log('Retrieving LinkUp API key from Secrets Manager');
    const command = new GetSecretValueCommand({
      SecretId: SEARCH_API_SECRET_ARN
    });
    const secretData = await secretsManager.send(command);
    
    if (!secretData.SecretString) {
      throw new Error('Secret string is empty');
    }
    
    const secretJson = JSON.parse(secretData.SecretString);
    LINKUP_API_KEY = secretJson.apiKey;
    
    if (!LINKUP_API_KEY) {
      throw new Error('API key not found in secret');
    }
    
    console.log('Successfully retrieved LinkUp API key from Secrets Manager');
    return LINKUP_API_KEY;
  } catch (error) {
    console.error('Error retrieving LinkUp API key from Secrets Manager:', error);
    throw error;
  }
}

/**
 * Perform a search using LinkUp API
 */
async function performLinkUpSearch(query: string): Promise<any> {
  try {
    console.log(`Performing LinkUp search for: ${query}`);
    
    // Get the API key from Secrets Manager
    const apiKey = await getApiKey();
    
    // Initialize LinkUp client
    const client = new LinkupClient({ apiKey });
    
    const response = await client.search({
      query: query,
      depth: "standard",
      outputType: "searchResults",
      includeImages: false,
    });
    
    console.log('LinkUp search completed successfully');
    console.log('Number of results:', response.results?.length || 0);
    
    // Log the raw response structure (similar to LinkUp console)
    console.log('Raw LinkUp response:');
    console.log(JSON.stringify(response, null, 2));
    
    return response;
  } catch (error) {
    console.error('Error performing LinkUp search:', error);
    throw error;
  }
}

/**
 * Send a result event to EventBridge
 */
async function sendResultEvent(invocationId: string, agentInvocationId: string, toolName: string, searchResults: any): Promise<void> {
  try {
    console.log('Sending search results to EventBridge');
    
    const command = new PutEventsCommand({
      Entries: [
        {
          EventBusName: process.env.EVENT_BUS_NAME,
          Source: 'research-agent',
          DetailType: 'ToolExecuted',
          Detail: JSON.stringify({
            invocationId: invocationId,
            agentInvocationId: agentInvocationId,
            toolName: toolName,
            result: searchResults
          })
        }
      ]
    });
    await eventBridge.send(command);
    
    console.log('Successfully sent search results event');
  } catch (error) {
    console.error('Error sending result event:', error);
    throw error;
  }
}

/**
 * Lambda handler
 */
export const handler = async (event: EventBridgeEvent<'ToolInvoked', EventDetail>, context: Context): Promise<any> => {
  console.log('Received event:', JSON.stringify(event));
  
  // Extract the search query and invocation ID from the event
  const detail = event.detail || {};
  const invocationId = detail.invocationId;
  const agentInvocationId = detail.agentInvocationId;
  const toolName = detail.toolName;
  const args = detail.arguments || {};
  const query = args.query;

  try {
    
    if (toolName !== 'performSearch') {
      throw new Error(`Unexpected tool name: ${toolName}, expected 'performSearch'`);
    }
    
    if (!query) {
      throw new Error('Missing query parameter in arguments');
    }
    
    if (!invocationId) {
      throw new Error('Missing invocationId parameter');
    }
    
    // Perform the search using LinkUp
    const searchResults = await performLinkUpSearch(query);
    
    // Limit to 10 results
    const limitedResults = {
      ...searchResults,
      results: (searchResults.results || []).slice(0, MAX_RESULTS)
    };
    
    console.log(`Returning ${limitedResults.results.length} search results`);
    
    // Send the raw results to EventBridge
    await sendResultEvent(invocationId, agentInvocationId, toolName, limitedResults);
    
    return {
      statusCode: 200,
      body: JSON.stringify({
        message: 'Search completed successfully',
        invocationId
      })
    };
  } catch (error: any) {
    console.error('Error:', error);

    await sendResultEvent(invocationId, agentInvocationId, toolName, { error: error.message });
    
    return {
      statusCode: 500,
      body: JSON.stringify({
        error: error.message
      })
    };
  }
};
