import { EventBridgeEvent, Context } from 'aws-lambda';

interface ToolInvokedEventDetail {
  invocationId: string;
  agentInvocationId: string;
  toolName: string;
  timestamp?: string;
}

interface ToolExecutedEventDetail {
  invocationId: string;
  agentInvocationId: string;
  toolName: string;
  timestamp?: string;
}

interface ToolStatusUpdate {
  invocationId: string;
  agentInvocationId: string;
  toolName: string;
  status: 'invoked' | 'executed';
  message: string;
  timestamp: string;
}

type ToolInvokedEvent = EventBridgeEvent<'ToolInvoked', ToolInvokedEventDetail>;
type ToolExecutedEvent = EventBridgeEvent<'ToolExecuted', ToolExecutedEventDetail>;
type ToolEvent = ToolInvokedEvent | ToolExecutedEvent;

const TOOL_NAME_MAPPINGS: Record<string, string> = {
  'performSearch': 'Researching information',
  'generatePDF': 'Generating research report',
  'requestHumanReview': 'Requesting human review',
  'queryDocument': 'Analyzing documents'
};

export const handler = async (event: ToolEvent, context: Context): Promise<void> => {
  console.log('Received tool event:', JSON.stringify(event, null, 2));
  
  try {
    const { detail, 'detail-type': detailType } = event;
    const { invocationId, agentInvocationId, toolName } = detail;

    if (!invocationId || !agentInvocationId || !toolName) {
      throw new Error('Missing required fields: invocationId, agentInvocationId and toolName');
    }

    const status = detailType === 'ToolInvoked' ? 'invoked' : 'executed';
    const message = generateStatusMessage(toolName, status);

    const toolStatusUpdate: ToolStatusUpdate = {
      invocationId,
      agentInvocationId,
      toolName,
      status,
      message,
      timestamp: new Date().toISOString(),
    };

    await publishToolStatusToAppSync(toolStatusUpdate);

    console.log('Successfully processed tool status update');

  } catch (error) {
    console.error('Error processing tool event:', error);
    throw error;
  }
};

function generateStatusMessage(toolName: string, status: 'invoked' | 'executed'): string {
  const toolMessage = TOOL_NAME_MAPPINGS[toolName] || `Using ${toolName} tool`;
  
  if (status === 'invoked') {
    return toolMessage;
  } else {
    return 'AI Researcher Thinking';
  }
}

async function publishToolStatusToAppSync(toolStatusUpdate: ToolStatusUpdate): Promise<void> {
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
        channel: `/agent/${toolStatusUpdate.agentInvocationId}`,
        events: [JSON.stringify({
          type: 'toolStatus',
          ...toolStatusUpdate
        })]
      })
    });

    if (!response.ok) {
      const errorText = await response.text().catch(() => 'Unknown error');
      throw new Error(`AppSync request failed: ${response.status} ${response.statusText} - ${errorText}`);
    }
    
    console.log('Successfully published tool status to AppSync Events');
  } catch (error) {
    console.error('Error publishing tool status to AppSync Events API:', error);
  }
}