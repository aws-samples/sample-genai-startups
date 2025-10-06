import { Construct } from 'constructs';
import { Duration, RemovalPolicy, CfnOutput, Stack } from 'aws-cdk-lib';
import * as events from 'aws-cdk-lib/aws-events';
import * as targets from 'aws-cdk-lib/aws-events-targets';
import * as lambda from 'aws-cdk-lib/aws-lambda';
import * as nodejs from 'aws-cdk-lib/aws-lambda-nodejs';
import * as s3 from 'aws-cdk-lib/aws-s3';
import * as iam from 'aws-cdk-lib/aws-iam';
import * as dynamodb from 'aws-cdk-lib/aws-dynamodb';
import * as appsync from 'aws-cdk-lib/aws-appsync';
import * as apigateway from 'aws-cdk-lib/aws-apigateway';

export interface ToolHumanReviewerConstructProps {
  eventBus: events.EventBus;
  documentsBucket: s3.Bucket;
}

export class ToolHumanReviewerConstruct extends Construct {
  public readonly incomingLambda: lambda.Function;
  public readonly table: dynamodb.Table;
  public readonly eventsApi: appsync.EventApi;
  public readonly eventsApiKey: appsync.CfnApiKey;
  public readonly outgoingLambda: lambda.Function;
  public readonly api: apigateway.RestApi;

  constructor(scope: Construct, id: string, props: ToolHumanReviewerConstructProps) {
    super(scope, id);

    // Create DynamoDB table for human review requests
    this.table = new dynamodb.Table(this, 'ReviewTable', {
      partitionKey: {
        name: 'id',
        type: dynamodb.AttributeType.STRING
      },
      billingMode: dynamodb.BillingMode.PAY_PER_REQUEST,
      removalPolicy: RemovalPolicy.DESTROY,
    });

    // Create AppSync Events API for real-time notifications
    this.eventsApi = new appsync.EventApi(this, 'EventsApi', {
      apiName: `${Stack.of(this).stackName}-human-reviewer-events-api`,
      authorizationConfig: {
        authProviders: [{
          authorizationType: appsync.AppSyncAuthorizationType.API_KEY
        }]
      }
    });

    this.eventsApiKey = new appsync.CfnApiKey(this, 'ReviewerEventsApiKey', {
      apiId: this.eventsApi.apiId,
      expires: Math.floor(new Date().setDate(new Date().getDate() + 365) / 1000.0), // Expires in 1 year
    });

    this.eventsApi.addChannelNamespace('human-reviewer');

    // Lambda function to handle incoming ToolInvoked events
    this.incomingLambda = new nodejs.NodejsFunction(this, 'IncomingLambda', {
      entry: 'src/tool-human-reviewer/lambdas/in.ts',
      handler: 'handler',
      runtime: lambda.Runtime.NODEJS_22_X,
      timeout: Duration.minutes(2),
      memorySize: 256,
      environment: {
        TABLE_NAME: this.table.tableName,
        DOCUMENTS_BUCKET_NAME: props.documentsBucket.bucketName,
        EVENTS_API_URL: `https://${this.eventsApi.httpDns}/event`,
        EVENTS_API_KEY: this.eventsApiKey.attrApiKey,
      },
    });

    // Grant permissions to incoming lambda
    props.documentsBucket.grantRead(this.incomingLambda);
    this.table.grantWriteData(this.incomingLambda);

    // EventBridge rule to trigger incoming lambda
    const rule = new events.Rule(this, 'ToolInvokeRule', {
      eventBus: props.eventBus,
      eventPattern: {
        detailType: ['ToolInvoked'],
        detail: {
          toolName: ['requestHumanReview']
        }
      }
    });

    rule.addTarget(new targets.LambdaFunction(this.incomingLambda));

    // Lambda function for getting pending reviews
    const getReviewsLambda = new nodejs.NodejsFunction(this, 'GetReviewsLambda', {
      entry: 'src/tool-human-reviewer/lambdas/get.ts',
      handler: 'handler',
      runtime: lambda.Runtime.NODEJS_22_X,
      timeout: Duration.minutes(1),
      memorySize: 256,
      environment: {
        TABLE_NAME: this.table.tableName,
      },
    });

    this.table.grantReadData(getReviewsLambda);

    // Lambda function for submitting review decisions
    this.outgoingLambda = new nodejs.NodejsFunction(this, 'OutgoingLambda', {
      entry: 'src/tool-human-reviewer/lambdas/out.ts',
      handler: 'handler',
      runtime: lambda.Runtime.NODEJS_22_X,
      timeout: Duration.minutes(1),
      memorySize: 256,
      environment: {
        EVENT_BUS_NAME: props.eventBus.eventBusName,
        TABLE_NAME: this.table.tableName,
      },
    });

    this.table.grantReadWriteData(this.outgoingLambda);
    this.outgoingLambda.addToRolePolicy(new iam.PolicyStatement({
      effect: iam.Effect.ALLOW,
      actions: ['events:PutEvents'],
      resources: [props.eventBus.eventBusArn]
    }));

    // API Gateway for frontend interactions
    this.api = new apigateway.RestApi(this, 'Api', {
      defaultCorsPreflightOptions: {
        allowOrigins: apigateway.Cors.ALL_ORIGINS,
        allowMethods: apigateway.Cors.ALL_METHODS,
        allowHeaders: ['Content-Type', 'Authorization'],
      },
    });

    const reviewsResource = this.api.root.addResource('reviews');
    reviewsResource.addMethod('GET', new apigateway.LambdaIntegration(getReviewsLambda));
    reviewsResource.addMethod('POST', new apigateway.LambdaIntegration(this.outgoingLambda));

    // Outputs for frontend
    new CfnOutput(this, 'EventsApiRealtimeDNS', {
      value: this.eventsApi.realtimeDns,
    });

    new CfnOutput(this, 'EventsApiKey', {
      value: this.eventsApiKey.attrApiKey,
    });

    new CfnOutput(this, 'ApiUrl', {
      value: this.api.url,
    });
  }
}
