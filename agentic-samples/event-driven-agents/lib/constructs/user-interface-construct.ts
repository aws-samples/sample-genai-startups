import { Construct } from 'constructs';
import { Duration, CfnOutput, Stack } from 'aws-cdk-lib';
import * as events from 'aws-cdk-lib/aws-events';
import * as targets from 'aws-cdk-lib/aws-events-targets';
import * as lambda from 'aws-cdk-lib/aws-lambda';
import * as nodejs from 'aws-cdk-lib/aws-lambda-nodejs';
import * as s3 from 'aws-cdk-lib/aws-s3';
import * as iam from 'aws-cdk-lib/aws-iam';
import * as appsync from 'aws-cdk-lib/aws-appsync';
import * as apigateway from 'aws-cdk-lib/aws-apigateway';

export interface UserInterfaceConstructProps {
  eventBus: events.EventBus;
  documentsBucket: s3.Bucket;
}

export class UserInterfaceConstruct extends Construct {
  public readonly submitLambda: lambda.Function;
  public readonly responseLambda: lambda.Function;
  public readonly toolStatusLambda: lambda.Function;
  public readonly eventsApi: appsync.EventApi;
  public readonly eventsApiKey: appsync.CfnApiKey;
  public readonly api: apigateway.RestApi;

  constructor(scope: Construct, id: string, props: UserInterfaceConstructProps) {
    super(scope, id);

    // Create AppSync Events API for real-time notifications
    this.eventsApi = new appsync.EventApi(this, 'EventsApi', {
      apiName: `${Stack.of(this).stackName}-user-interface-events-api`,
      authorizationConfig: {
        authProviders: [{
          authorizationType: appsync.AppSyncAuthorizationType.API_KEY
        }]
      }
    });

    this.eventsApiKey = new appsync.CfnApiKey(this, 'UserEventsApiKey', {
      apiId: this.eventsApi.apiId,
      expires: Math.floor(new Date().setDate(new Date().getDate() + 365) / 1000.0), // Expires in 1 year
    });

    this.eventsApi.addChannelNamespace('agent');

    // Lambda function to handle user request submission
    this.submitLambda = new nodejs.NodejsFunction(this, 'SubmitLambda', {
      entry: 'src/user-interface/lambdas/submit.ts',
      handler: 'handler',
      runtime: lambda.Runtime.NODEJS_22_X,
      timeout: Duration.minutes(2),
      memorySize: 256,
      environment: {
        EVENT_BUS_NAME: props.eventBus.eventBusName,
      },
    });

    // Grant permissions to submit lambda
    this.submitLambda.addToRolePolicy(new iam.PolicyStatement({
      effect: iam.Effect.ALLOW,
      actions: ['events:PutEvents'],
      resources: [props.eventBus.eventBusArn]
    }));

    // Lambda function to handle AgentExecuted events and send response
    this.responseLambda = new nodejs.NodejsFunction(this, 'ResponseLambda', {
      entry: 'src/user-interface/lambdas/response.ts',
      handler: 'handler',
      runtime: lambda.Runtime.NODEJS_22_X,
      timeout: Duration.minutes(2),
      memorySize: 256,
      environment: {
        DOCUMENTS_BUCKET_NAME: props.documentsBucket.bucketName,
        EVENTS_API_URL: `https://${this.eventsApi.httpDns}/event`,
        EVENTS_API_KEY: this.eventsApiKey.attrApiKey,
      },
    });

    // Grant permissions to response lambda
    props.documentsBucket.grantRead(this.responseLambda);

    // EventBridge rule to trigger response lambda on AgentExecuted events
    const rule = new events.Rule(this, 'AgentExecutedRule', {
      eventBus: props.eventBus,
      eventPattern: {
        detailType: ['AgentExecuted'],
        source: ['edagent.orchestrator']
      }
    });

    rule.addTarget(new targets.LambdaFunction(this.responseLambda));

    // Lambda function to handle tool status updates
    this.toolStatusLambda = new nodejs.NodejsFunction(this, 'ToolStatusLambda', {
      entry: 'src/user-interface/lambdas/tool-status.ts',
      handler: 'handler',
      runtime: lambda.Runtime.NODEJS_22_X,
      timeout: Duration.minutes(2),
      memorySize: 256,
      environment: {
        EVENTS_API_URL: `https://${this.eventsApi.httpDns}/event`,
        EVENTS_API_KEY: this.eventsApiKey.attrApiKey,
      },
    });

    // EventBridge rules for tool events
    const toolInvokedRule = new events.Rule(this, 'ToolInvokedRule', {
      eventBus: props.eventBus,
      eventPattern: {
        detailType: ['ToolInvoked']
      }
    });

    const toolExecutedRule = new events.Rule(this, 'ToolExecutedRule', {
      eventBus: props.eventBus,
      eventPattern: {
        detailType: ['ToolExecuted']
      }
    });

    toolInvokedRule.addTarget(new targets.LambdaFunction(this.toolStatusLambda));
    toolExecutedRule.addTarget(new targets.LambdaFunction(this.toolStatusLambda));

    // API Gateway for frontend interactions
    this.api = new apigateway.RestApi(this, 'Api', {
      defaultCorsPreflightOptions: {
        allowOrigins: apigateway.Cors.ALL_ORIGINS,
        allowMethods: apigateway.Cors.ALL_METHODS,
        allowHeaders: ['Content-Type', 'Authorization'],
      },
    });

    const queryResource = this.api.root.addResource('query');
    queryResource.addMethod('POST', new apigateway.LambdaIntegration(this.submitLambda));

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