import { Construct } from 'constructs';
import * as events from 'aws-cdk-lib/aws-events';
import * as targets from 'aws-cdk-lib/aws-events-targets';
import * as s3 from 'aws-cdk-lib/aws-s3';
import * as lambda from 'aws-cdk-lib/aws-lambda';
import * as nodejs from 'aws-cdk-lib/aws-lambda-nodejs';
import * as iam from 'aws-cdk-lib/aws-iam';
import * as dynamodb from 'aws-cdk-lib/aws-dynamodb';
import * as sfn from 'aws-cdk-lib/aws-stepfunctions';
import * as path from 'path';
import { Duration, RemovalPolicy } from 'aws-cdk-lib';

export interface OrchestratorConstructProps {
  eventBus: events.EventBus;
  documentsBucket: s3.Bucket;
}

export class OrchestratorConstruct extends Construct {
  public readonly agentLambda: nodejs.NodejsFunction;
  public readonly callbackLambda: nodejs.NodejsFunction;
  public readonly conversationTable: dynamodb.Table;
  public readonly agentStateMachine: sfn.StateMachine;

  constructor(scope: Construct, id: string, props: OrchestratorConstructProps) {
    super(scope, id);

    this.conversationTable = new dynamodb.Table(this, 'ConversationHistoryTable', {
      partitionKey: {
        name: 'invocationId',
        type: dynamodb.AttributeType.STRING,
      },
      sortKey: {
        name: 'timestamp',
        type: dynamodb.AttributeType.STRING,
      },
      billingMode: dynamodb.BillingMode.PAY_PER_REQUEST,
      removalPolicy: RemovalPolicy.DESTROY
    });

    this.agentLambda = new nodejs.NodejsFunction(this, 'AgentLambda', {
      entry: 'src/orchestrator/lambdas/agent.ts',
      handler: 'handler',
      runtime: lambda.Runtime.NODEJS_22_X,
      timeout: Duration.minutes(15),
      memorySize: 1024,
      environment: {
        CONVERSATION_TABLE_NAME: this.conversationTable.tableName,
      },
    });

    this.agentLambda.addToRolePolicy(
      new iam.PolicyStatement({
        effect: iam.Effect.ALLOW,
        actions: ['bedrock:InvokeModel'],
        resources: ['*'], // TODO: I know I know but we are currently testing with different models
      })
    );

    this.conversationTable.grantReadWriteData(this.agentLambda);

    // Create the Step Functions state machine using definitionBody.fromFile
    this.agentStateMachine = new sfn.StateMachine(this, 'AgentOrchestrator', {
      definitionBody: sfn.DefinitionBody.fromFile(path.join(__dirname, '../../src/orchestrator/state-machines/agent.asl.json')),
      definitionSubstitutions: {
        AgentLambdaFunction: this.agentLambda.functionArn,
        ToolUseEventBus: props.eventBus.eventBusName
      },
      stateMachineType: sfn.StateMachineType.STANDARD,
      tracingEnabled: true,
    });

    this.agentLambda.grantInvoke(this.agentStateMachine);
    props.eventBus.grantPutEventsTo(this.agentStateMachine);

    // Create callback lambda for handling ToolExecuted events
    this.callbackLambda = new nodejs.NodejsFunction(this, 'CallbackLambda', {
      entry: 'src/orchestrator/lambdas/callback.ts',
      handler: 'handler',
      runtime: lambda.Runtime.NODEJS_22_X,
      timeout: Duration.minutes(5),
      memorySize: 256,
    });

    // Grant the callback lambda permission to send task success/failure to Step Functions
    this.callbackLambda.addToRolePolicy(
      new iam.PolicyStatement({
        effect: iam.Effect.ALLOW,
        actions: ['states:SendTaskSuccess', 'states:SendTaskFailure'],
        resources: [this.agentStateMachine.stateMachineArn],
      })
    );

    // Create EventBridge rule to trigger callback lambda on ToolExecuted events
    const toolExecutedRule = new events.Rule(this, 'ToolExecutedRule', {
      eventBus: props.eventBus,
      eventPattern: {
        detailType: ['ToolExecuted'],
      },
      description: 'Triggers callback lambda when tools complete execution',
    });

    // Add the callback lambda as a target for the rule
    toolExecutedRule.addTarget(new targets.LambdaFunction(this.callbackLambda));

    // Create EventBridge rule to trigger Step Function on AgentInvoked events
    const agentInvokedRule = new events.Rule(this, 'AgentInvokedRule', {
      eventBus: props.eventBus,
      eventPattern: {
        detailType: ['AgentInvoked']
      },
      description: 'Triggers Step Function when agent invocation is requested',
    });

    // Add the Step Function as a target for AgentInvoked events
    agentInvokedRule.addTarget(new targets.SfnStateMachine(this.agentStateMachine, {
      input: events.RuleTargetInput.fromEventPath('$.detail')
    }));

    // Grant EventBridge permission to start the Step Function
    this.agentStateMachine.grantStartExecution(new iam.ServicePrincipal('events.amazonaws.com'));
  }
}
