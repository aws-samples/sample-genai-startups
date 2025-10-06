import { SFNClient, SendTaskSuccessCommand, SendTaskFailureCommand } from "@aws-sdk/client-sfn";
import { EventBridgeEvent } from "aws-lambda";

const client = new SFNClient();

interface ToolExecutedDetail {
  invocationId: string; // This is the SFN task token
  result: string; // Plain result from the tool
}

export const handler = async (event: EventBridgeEvent<'ToolExecuted', ToolExecutedDetail>) => {
  try {
    console.log('Received ToolExecuted event:', JSON.stringify(event, null, 2));

    if (event["detail-type"] !== 'ToolExecuted') {
      throw new Error(`Unexpected event type: ${event["detail-type"]}`);
    }

    const { invocationId, result } = event.detail;

    if (!invocationId) {
      throw new Error('Missing invocationId (task token) in event detail');
    }

    // Send the plain result back to Step Functions
    const input = {
      taskToken: invocationId,
      output: JSON.stringify(result)
    };

    const command = new SendTaskSuccessCommand(input);
    await client.send(command);

    console.log('Successfully resumed Step Functions execution');

  } catch (error) {
    console.error('Error processing ToolExecuted event:', error);
    
    try {
      const input = {
        taskToken: event.detail?.invocationId,
        error: error instanceof Error ? error.message : "Unknown error"
      };
      
      if (input.taskToken) {
        const command = new SendTaskFailureCommand(input);
        await client.send(command);
        console.log('Sent task failure to Step Functions');
      }
    } catch (failureError) {
      console.error('Failed to send task failure:', failureError);
    }
  }
};
