import * as cdk from 'aws-cdk-lib';
import { Construct } from 'constructs';
import * as events from 'aws-cdk-lib/aws-events';
import * as targets from 'aws-cdk-lib/aws-events-targets';
import * as logs from 'aws-cdk-lib/aws-logs';
import * as s3 from 'aws-cdk-lib/aws-s3';
import { NagSuppressions } from 'cdk-nag';
import { OrchestratorConstruct } from './constructs/orchestrator-construct';
import { ToolHumanReviewerConstruct } from './constructs/tool-human-reviewer-construct';
import { ToolSearchAgentConstruct } from './constructs/tool-search-agent-construct';
import { ToolDocumentQuerierConstruct } from './constructs/tool-document-querier-construct';
import { ToolPdfGeneratorConstruct } from './constructs/tool-pdf-generator-construct';
import { UserInterfaceConstruct } from './constructs/user-interface-construct';

export class EventDrivenAgentsStack extends cdk.Stack {
  constructor(scope: Construct, id: string, props?: cdk.StackProps) {
    super(scope, id, props);

    // EventBridge custom bus for research agent
    const researchAgentBus = new events.EventBus(this, 'ResearchAgentBus', {
      eventBusName: `${this.stackName}-${cdk.Aws.ACCOUNT_ID}-${cdk.Aws.REGION}-research-agent-bus`,
      description: 'Custom EventBridge bus for research agent events'
    });

    // CloudWatch Log Group for debugging all events
    const eventDebugLogGroup = new logs.LogGroup(this, 'EventDebugLogGroup', {
      logGroupName: `/aws/events/${this.stackName}-${cdk.Aws.ACCOUNT_ID}-${cdk.Aws.REGION}-research-agent-bus-debug`,
      retention: logs.RetentionDays.ONE_WEEK,
      removalPolicy: cdk.RemovalPolicy.DESTROY
    });

    // Catch-all rule to log all events for debugging
    new events.Rule(this, 'CatchAllDebugRule', {
      eventBus: researchAgentBus,
      eventPattern: {
        account: [cdk.Aws.ACCOUNT_ID]
      },
      description: 'Catch-all rule to log all events on the research agent bus for debugging',
      targets: [
        new targets.CloudWatchLogGroup(eventDebugLogGroup)
      ]
    });

    // S3 bucket for documents with SSL enforcement
    const documentsBucket = new s3.Bucket(this, 'DocumentsBucket', {
      bucketName: `${this.stackName.toLowerCase()}-${cdk.Aws.ACCOUNT_ID}-${cdk.Aws.REGION}-documents-bucket`,
      versioned: true,
      encryption: s3.BucketEncryption.S3_MANAGED,
      blockPublicAccess: s3.BlockPublicAccess.BLOCK_ALL,
      removalPolicy: cdk.RemovalPolicy.DESTROY,
      autoDeleteObjects: true,
      enforceSSL: true
    });

    // Output the EventBridge bus ARN and S3 bucket name
    new cdk.CfnOutput(this, 'ResearchAgentBusArn', {
      value: researchAgentBus.eventBusArn,
      description: 'ARN of the Research Agent EventBridge bus'
    });

    new cdk.CfnOutput(this, 'DocumentsBucketName', {
      value: documentsBucket.bucketName,
      description: 'Name of the Documents S3 bucket'
    });

    new cdk.CfnOutput(this, 'EventDebugLogGroupName', {
      value: eventDebugLogGroup.logGroupName,
      description: 'CloudWatch Log Group for debugging EventBridge events'
    });

    // Create all constructs and pass the shared resources
    const orchestrator = new OrchestratorConstruct(this, 'Orchestrator', {
      eventBus: researchAgentBus,
      documentsBucket: documentsBucket
    });

    const humanReviewer = new ToolHumanReviewerConstruct(this, 'ToolHumanReviewer', {
      eventBus: researchAgentBus,
      documentsBucket: documentsBucket
    });

    const searchAgent = new ToolSearchAgentConstruct(this, 'ToolSearchAgent', {
      eventBus: researchAgentBus,
      documentsBucket: documentsBucket,
      linkupApiKey: process.env.LINKUP_API_KEY, // Get from environment variabl
    });

    const documentQuerier = new ToolDocumentQuerierConstruct(this, 'ToolDocumentQuerier', {
      eventBus: researchAgentBus,
      documentsBucket: documentsBucket
    });

    const pdfGenerator = new ToolPdfGeneratorConstruct(this, 'ToolPdfGenerator', {
      eventBus: researchAgentBus,
      documentsBucket: documentsBucket
    });

    const userInterface = new UserInterfaceConstruct(this, 'UserInterface', {
      eventBus: researchAgentBus,
      documentsBucket: documentsBucket
    });

    // Add CDK Nag suppressions for demo application
    this.addNagSuppressions();
  }

  private addNagSuppressions() {
    // Suppress demo-appropriate issues
    NagSuppressions.addStackSuppressions(this, [
      {
        id: 'AwsSolutions-IAM4',
        reason: 'AWS managed policies are appropriate for Lambda basic execution roles in demo'
      },
      {
        id: 'AwsSolutions-IAM5',
        reason: 'Wildcard permissions required for CloudWatch Logs, EventBridge, and S3 operations in demo'
      },
      {
        id: 'AwsSolutions-L1',
        reason: 'CDK internal Lambda functions (custom resources) - runtime managed by CDK framework'
      },
      {
        id: 'AwsSolutions-S1',
        reason: 'Access logs not required for demo application'
      },
      {
        id: 'AwsSolutions-SMG4',
        reason: 'API key rotation managed externally by Linkup service provider'
      },
      {
        id: 'AwsSolutions-APIG1',
        reason: 'API Gateway access logging not required for demo application'
      },
      {
        id: 'AwsSolutions-APIG2',
        reason: 'Request validation not implemented in demo - would be added in production'
      },
      {
        id: 'AwsSolutions-APIG3',
        reason: 'WAF not required for demo application'
      },
      {
        id: 'AwsSolutions-APIG4',
        reason: 'Authentication not implemented in demo - would use Cognito in production'
      },
      {
        id: 'AwsSolutions-APIG6',
        reason: 'CloudWatch logging not required for demo API Gateway'
      },
      {
        id: 'AwsSolutions-COG4',
        reason: 'Cognito authentication not implemented in demo - would be added in production'
      },
      {
        id: 'AwsSolutions-DDB3',
        reason: 'Point-in-time recovery not required for demo DynamoDB tables'
      },
      {
        id: 'AwsSolutions-SF1',
        reason: 'Step Functions detailed logging not required for demo'
      }
    ]);
  }
}
