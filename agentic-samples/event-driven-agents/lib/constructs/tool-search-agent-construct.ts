import { Construct } from 'constructs';
import * as events from 'aws-cdk-lib/aws-events';
import * as s3 from 'aws-cdk-lib/aws-s3';
import * as lambda from 'aws-cdk-lib/aws-lambda';
import * as nodejs from 'aws-cdk-lib/aws-lambda-nodejs';
import * as iam from 'aws-cdk-lib/aws-iam';
import * as targets from 'aws-cdk-lib/aws-events-targets';
import * as logs from 'aws-cdk-lib/aws-logs';
import * as path from 'path';
import * as cdk from 'aws-cdk-lib';
import * as nodejsLambda from 'aws-cdk-lib/aws-lambda-nodejs';
import * as secretsmanager from 'aws-cdk-lib/aws-secretsmanager';
import { Duration, Stack } from 'aws-cdk-lib';


export interface ToolSearchAgentConstructProps {
  eventBus: events.EventBus;
  documentsBucket: s3.Bucket;
  linkupApiKey?: string; // LinkUp API key can be passed during deployment
}

export class ToolSearchAgentConstruct extends Construct {
  public readonly searchFunction: nodejsLambda.NodejsFunction;
  public readonly apiKeySecret: secretsmanager.Secret;

  constructor(scope: Construct, id: string, props: ToolSearchAgentConstructProps) {
    super(scope, id);

    // Create a secret for the LinkUp API key
    this.apiKeySecret = new secretsmanager.Secret(this, 'LinkupApiKey', {
      secretName: `${Stack.of(this).stackName}-research-agent-linkup-api-key`,
      description: 'API key for LinkUp Search',
      generateSecretString: {
        secretStringTemplate: JSON.stringify({ 
          apiKey: props.linkupApiKey || 'placeholder-update-me' 
        }),
        generateStringKey: 'dummy' // Not used but required
      }
    });

    // Create a Lambda function for the search agent using NodejsFunction
    this.searchFunction = new nodejs.NodejsFunction(this, 'SearchFunction', {
      entry: 'src/tool-search-agent/lambdas/index.ts',
      handler: 'handler',
      runtime: lambda.Runtime.NODEJS_22_X,
      timeout: Duration.minutes(5),
      memorySize: 512,
      logRetention: logs.RetentionDays.ONE_WEEK,
      environment: {
        EVENT_BUS_NAME: props.eventBus.eventBusName,
        SEARCH_API_SECRET_ARN: this.apiKeySecret.secretArn
      }
    });

    // Grant the Lambda function permission to read the secret
    this.apiKeySecret.grantRead(this.searchFunction);

    // Grant the Lambda function permissions to put events on the EventBridge bus
    this.searchFunction.addToRolePolicy(
      new iam.PolicyStatement({
        actions: ['events:PutEvents'],
        resources: [props.eventBus.eventBusArn]
      })
    );

    // Create an EventBridge rule to trigger the search function
    const searchRequestRule = new events.Rule(this, 'SearchRequestRule', {
      eventBus: props.eventBus,
      description: 'Rule to capture tool invocation requests for search',
      eventPattern: {
        detailType: ['ToolInvoked'],
        detail: {
          toolName: ['performSearch']
        }
      }
    });

    // Add the Lambda function as a target for the rule
    searchRequestRule.addTarget(new targets.LambdaFunction(this.searchFunction));
  }
}
