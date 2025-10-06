import { Handler, EventBridgeEvent } from 'aws-lambda';
import { S3Client, PutObjectCommand } from '@aws-sdk/client-s3';
import { EventBridgeClient, PutEventsCommand } from '@aws-sdk/client-eventbridge';
import puppeteer from 'puppeteer-core';
import { v4 as uuidv4 } from 'uuid';

interface ToolInvokedDetail {
  toolName: string;
  invocationId: string;
  agentInvocationId: string;
  arguments: {
    html: string;
  };
}

type PdfGeneratorEvent = EventBridgeEvent<'ToolInvoked', ToolInvokedDetail>;

const s3Client = new S3Client({});
const eventBridgeClient = new EventBridgeClient({});

export const handler: Handler<PdfGeneratorEvent, void> = async (event) => {
  console.log('PDF Generator Lambda triggered with event:', JSON.stringify(event, null, 2));

  const { detail } = event;
  const { invocationId, agentInvocationId, toolName, arguments: args } = detail;
  const { html } = args;
  let browser;

  try {
    if (!html) {
      throw new Error('HTML content is required!');
    }

    const bucketName = process.env.DOCUMENTS_BUCKET_NAME;
    if (!bucketName) {
      throw new Error('DOCUMENTS_BUCKET_NAME environment variable is required');
    }

    console.log('=== Chromium Debug Info ===');
    console.log('Memory usage:', JSON.stringify(process.memoryUsage(), null, 2));
    console.log('Lambda /tmp directory size:', require('child_process').execSync('du -sh /tmp').toString());
    console.log('/tmp contents:', require('fs').readdirSync('/tmp'));
    
    // Dynamic import of chromium ES module
    console.log('Importing chromium module...');
    const chromium = await import('@sparticuz/chromium');
    console.log('Chromium module imported successfully');
    
    console.log('Attempting to get executable path...');
    const executablePath = await chromium.default.executablePath(
      process.env.AWS_EXECUTION_ENV 
        ? '/opt/nodejs/node_modules/@sparticuz/chromium/bin'
        : undefined
    );
    console.log('Executable path result:', executablePath);
    
    if (!executablePath) {
      throw new Error('Chromium executable path is undefined - extraction failed');
    }

    console.log('Launching browser...');
    browser = await puppeteer.launch({
      args: puppeteer.defaultArgs({ args: chromium.default.args, headless: 'shell' }),
      executablePath: executablePath,
      headless: 'shell',
    });

    const page = await browser.newPage();
    
    await page.setContent(html, {
      waitUntil: ['networkidle0', 'domcontentloaded'],
      timeout: 30000,
    });

    const pdfBuffer = await page.pdf({
      format: 'A4',
      landscape: false,
      margin: {
        top: '2.5cm',
        right: '2cm',
        bottom: '2.5cm',
        left: '2cm',
      },
      printBackground: true,
      scale: 1,
      timeout: 30000,
    });

    const timestamp = new Date().toISOString().replace(/[:.]/g, '-');
    const uniqueId = uuidv4().substring(0, 8);
    const key = `research-reports/report-${timestamp}-${uniqueId}.pdf`;

    const putObjectCommand = new PutObjectCommand({
      Bucket: bucketName,
      Key: key,
      Body: pdfBuffer,
      ContentType: 'application/pdf',
      Metadata: {
        'generated-at': new Date().toISOString(),
        'document-type': 'research-report',
      },
    });

    await s3Client.send(putObjectCommand);

    const s3Uri = `s3://${bucketName}/${key}`;

    console.log(`Research report PDF generated: ${s3Uri}`);

    // Emit ToolExecuted event
    const toolExecutedEvent = {
      Source: 'pdf-generator',
      DetailType: 'ToolExecuted',
      Detail: JSON.stringify({
        invocationId,
        agentInvocationId,
        toolName,
        result: JSON.stringify({ s3Uri }),
      }),
      EventBusName: process.env.EVENT_BUS_NAME,
    };

    await eventBridgeClient.send(new PutEventsCommand({
      Entries: [toolExecutedEvent],
    }));

    console.log('ToolExecuted event emitted for invocation:', invocationId);

  } catch (error: any) {
    console.error('Error generating PDF:', error);
    
    // Emit ToolExecuted event with error
    const toolExecutedEvent = {
      Source: 'pdf-generator',
      DetailType: 'ToolExecuted',
      Detail: JSON.stringify({
        invocationId,
        agentInvocationId,
        toolName,
        result: JSON.stringify({ error: error.message }),
      }),
      EventBusName: process.env.EVENT_BUS_NAME,
    };

    await eventBridgeClient.send(new PutEventsCommand({
      Entries: [toolExecutedEvent],
    }));

    throw error;
  } finally {
    if (browser) {
      await browser.close();
    }
  }
};