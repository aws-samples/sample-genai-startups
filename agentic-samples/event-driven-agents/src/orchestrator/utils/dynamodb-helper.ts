import { DynamoDBClient, QueryCommand, PutItemCommand } from '@aws-sdk/client-dynamodb';
import { marshall, unmarshall } from '@aws-sdk/util-dynamodb';
import type { MessageParam } from '@anthropic-ai/sdk/resources/messages/messages';

const dynamoClient = new DynamoDBClient();
const TABLE_NAME = process.env.CONVERSATION_TABLE_NAME;

interface ConversationRecord {
  invocationId: string;
  timestamp: string;
  role: MessageParam['role'];
  content: MessageParam['content'];
}

export async function getConversationHistory(invocationId: string): Promise<MessageParam[]> {
  try {
    const command = new QueryCommand({
      TableName: TABLE_NAME,
      KeyConditionExpression: 'invocationId = :invocationId',
      ExpressionAttributeValues: {
        ':invocationId': { S: invocationId }
      },
      ScanIndexForward: true, // Sort by timestamp ascending
      ConsistentRead: true // Ensure strong consistency
    });

    const result = await dynamoClient.send(command);
    
    if (!result.Items) {
      return [];
    }

    return result.Items.map(item => {
      const record = unmarshall(item) as ConversationRecord;
      return {
        role: record.role,
        content: record.content
      };
    });
  } catch (error) {
    console.error('Error retrieving conversation history:', error);
    return [];
  }
}

export async function saveMessage(invocationId: string, message: MessageParam): Promise<void> {
  try {
    const timestamp = new Date().toISOString();
    const record: ConversationRecord = {
      ...message,
      invocationId,
      timestamp
    };

    const command = new PutItemCommand({
      TableName: TABLE_NAME,
      Item: marshall(record)
    });

    await dynamoClient.send(command);
  } catch (error) {
    console.error('Error saving message:', error);
    throw error;
  }
}