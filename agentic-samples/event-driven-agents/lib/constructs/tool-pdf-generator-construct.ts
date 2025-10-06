import { Construct } from 'constructs';
import * as events from 'aws-cdk-lib/aws-events';
import * as targets from 'aws-cdk-lib/aws-events-targets';
import * as s3 from 'aws-cdk-lib/aws-s3';
import * as lambda from 'aws-cdk-lib/aws-lambda';
import * as nodejs from 'aws-cdk-lib/aws-lambda-nodejs';
import * as iam from 'aws-cdk-lib/aws-iam';
import { Duration } from 'aws-cdk-lib';

export interface ToolPdfGeneratorConstructProps {
  eventBus: events.EventBus;
  documentsBucket: s3.Bucket;
}

export class ToolPdfGeneratorConstruct extends Construct {
  public readonly pdfGeneratorLambda: nodejs.NodejsFunction;

  constructor(scope: Construct, id: string, props: ToolPdfGeneratorConstructProps) {
    super(scope, id);

    // Create a Lambda Layer for Chromium
    const chromiumLayer = new lambda.LayerVersion(this, 'ChromiumLayer', {
      code: lambda.Code.fromAsset('src/tool-pdf-generator/chromium-layer'),
      compatibleRuntimes: [lambda.Runtime.NODEJS_22_X],
      description: 'Chromium for PDF generation',
    });

    this.pdfGeneratorLambda = new nodejs.NodejsFunction(this, 'PdfGeneratorLambda', {
      entry: 'src/tool-pdf-generator/lambdas/html-to-pdf.ts',
      handler: 'handler',
      runtime: lambda.Runtime.NODEJS_22_X,
      timeout: Duration.minutes(5),
      memorySize: 3008,
      layers: [chromiumLayer],
      environment: {
        DOCUMENTS_BUCKET_NAME: props.documentsBucket.bucketName,
        EVENT_BUS_NAME: props.eventBus.eventBusName,
      },
      bundling: {
        // Chromium will be provided by layer
        externalModules: ['@sparticuz/chromium'],
        // Only bundle puppeteer-core
        nodeModules: ['puppeteer-core'],
        minify: false,
      },
    });

    props.documentsBucket.grantWrite(this.pdfGeneratorLambda);
    props.eventBus.grantPutEventsTo(this.pdfGeneratorLambda);

    const pdfGenerationRule = new events.Rule(this, 'PdfGenerationRule', {
      eventBus: props.eventBus,
      eventPattern: {
        detailType: ['ToolInvoked'],
        detail: {
          toolName: ['generatePDF'],
        },
      },
      description: 'Triggers PDF generation lambda when generatePdf tool is invoked',
    });

    pdfGenerationRule.addTarget(new targets.LambdaFunction(this.pdfGeneratorLambda));
  }
}
