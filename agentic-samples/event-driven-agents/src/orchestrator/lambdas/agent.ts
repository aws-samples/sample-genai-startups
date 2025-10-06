import { BedrockRuntimeClient, InvokeModelCommand } from '@aws-sdk/client-bedrock-runtime';
import type { MessageParam, Tool, Message } from '@anthropic-ai/sdk/resources/messages/messages';
import { getConversationHistory, saveMessage } from '../utils/dynamodb-helper';

const bedrockClient = new BedrockRuntimeClient();

const SYSTEM_PROMPT = `You are a research report creator assistant that helps generate comprehensive research reports based on user queries and optional document references. 

Your role is to:
1. Analyze the user's query and any provided documents
2. ALWAYS use available tools to research additional information helping answer the user query
3. Once enough information is available, generate a detailed, accurate research report in PDF
4. Request human review from a subject matter expert before finalizing and returning the results to the user

IMPORTANT GUIDELINES:
- Always think step-by-step about what information you need before using tools
- When you need multiple pieces of information, you MUST use multiple tools in parallel in a single response
- Plan your approach: identify all research needs, then execute searches concurrently
- For complex topics, consider breaking down into specific search queries that can run simultaneously
- Explain your reasoning when planning multiple searches or actions

Always maintain accuracy, cite sources and corresponding links when applicable, and follow proper research reporting standards. Use clear, professional language appropriate for comprehensive research documentation.`;

const TOOLS: Tool[] = [
  {
    name: 'performSearch',
    description: 'Perform search on the internet for additional information that could help in generating a quality research report. When possible you MUST use multiple concurrent searches for different aspects of complex topics (e.g., current trends, historical context, expert opinions, case studies).',
    input_schema: {
      type: 'object',
      properties: {
        query: {
          type: 'string',
          description: 'Specific, focused search query. For complex topics, break into multiple targeted searches that you MUST run in parallel.'
        }
      },
      required: ['query']
    }
  },
  // {
  //   name: 'queryDocument',
  //   description: 'Query a document uploaded by the user for specific information. Only use when the user has uploaded a document and you need to extract specific information from it (e.g., WBC levels, document summary, specific test results)',
  //   input_schema: {
  //     type: 'object',
  //     properties: {
  //       query: {
  //         type: 'string',
  //         description: 'What the agent wishes to check or extract from the document'
  //       },
  //       s3Uri: {
  //         type: 'string',
  //         description: 'S3 URI destination of the uploaded document'
  //       }
  //     },
  //     required: ['query', 's3Uri']
  //   }
  // },
  {
    name: 'generatePDF',
    description: 'Generate a PDF from HTML content that represents the final research report',
    input_schema: {
      type: 'object',
      properties: {
        html: {
          type: 'string',
          description: 'The HTML content representing the research report to be converted to PDF'
        }
      },
      required: ['html']
    }
  },
  {
    name: 'requestHumanReview',
    description: 'Request a review from a human subject matter expert for the generated research report',
    input_schema: {
      type: 'object',
      properties: {
        originalQuery: {
          type: 'string',
          description: 'The original user query that initiated the research report'
        },
        summary: {
          type: 'string',
          description: 'Summary of the research report findings and conclusions'
        },
        s3Uri: {
          type: 'string',
          description: 'If present, S3 URI of the generated PDF report'
        }
      },
      required: ['originalQuery', 'summary']
    }
  },
  {
    name: 'returnFinalAnswer',
    description: 'Return the final research report to the end user. This tool should ONLY be used after human review has been approved and all other steps are complete.',
    input_schema: {
      type: 'object',
      properties: {
        finalReportS3Uri: {
          type: 'string',
          description: 'If available, the S3 URI of the final approved research report PDF'
        },
        summary: {
          type: 'string',
          description: 'Brief summary of the research report findings for the user'
        },
        approved: {
          type: 'boolean',
          description: 'Whether the report has been approved (true) or rejected (false) by the subject matter expert'
        }
      },
      required: ['summary', 'approved']
    }
  }
];

interface AgentEvent {
  invocationId: string;
  message: MessageParam;
}

export const handler = async (event: AgentEvent): Promise<Message> => {
  try {
    const { invocationId, message } = event;

    // Save the incoming message to DynamoDB
    await saveMessage(invocationId, message);

    // Retrieve conversation history from DynamoDB
    const conversationHistory = await getConversationHistory(invocationId);

    console.log('CONVO HISTORY', JSON.stringify(conversationHistory))

    const requestBody = {
      anthropic_version: 'bedrock-2023-05-31',
      max_tokens: 32000,
      system: SYSTEM_PROMPT,
      messages: conversationHistory,
      tools: TOOLS,
      tool_choice: { type: 'any' }
    };

    const command = new InvokeModelCommand({
      modelId: 'us.anthropic.claude-sonnet-4-20250514-v1:0',
      body: JSON.stringify(requestBody),
      contentType: 'application/json',
      accept: 'application/json'
    });

    const response = await bedrockClient.send(command);
    const responseBody = JSON.parse(new TextDecoder().decode(response.body)) as Message;

    // Save the assistant's response to DynamoDB using the role from responseBody
    const assistantMessage: MessageParam = {
      role: responseBody.role,
      content: responseBody.content
    };
    await saveMessage(invocationId, assistantMessage);

    return responseBody;

  } catch (error) {
    console.error('Error invoking Claude:', error);
    throw new Error(`Failed to invoke Claude model: ${error instanceof Error ? error.message : 'Unknown error'}`);
  }
};
