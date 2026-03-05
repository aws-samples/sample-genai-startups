import { Stack, type StackProps, CfnOutput } from 'aws-cdk-lib';
import { Construct } from 'constructs';
import { DockerImageAsset, Platform } from 'aws-cdk-lib/aws-ecr-assets';
import { Role, ServicePrincipal, PolicyStatement, Effect } from 'aws-cdk-lib/aws-iam';
import { CfnRuntime } from 'aws-cdk-lib/aws-bedrockagentcore';

export interface AgentCoreStackProps extends StackProps {
  /** Project name from agentcore.json */
  projectName: string;
  /** Agent name from agentcore.json */
  agentName: string;
  /** Absolute path to the agent app directory containing the Dockerfile */
  appDir: string;
  networkMode?: 'PUBLIC' | 'VPC';
}

export class AgentCoreStack extends Stack {
  public readonly agentRuntimeId: string;

  constructor(scope: Construct, id: string, props: AgentCoreStackProps) {
    super(scope, id, props);

    const { projectName, agentName, appDir, networkMode = 'PUBLIC' } = props;

    const region = this.region;
    const account = this.account;

    // 1. Build and push the Docker image to ECR
    const imageAsset = new DockerImageAsset(this, 'AgentImage', {
      directory: appDir,
      platform: Platform.LINUX_ARM64,
    });

    // 2. IAM execution role for the AgentCore Runtime
    //    Trust policy follows AgentCore documentation requirements
    const executionRole = new Role(this, 'AgentExecutionRole', {
      assumedBy: new ServicePrincipal('bedrock-agentcore.amazonaws.com', {
        conditions: {
          StringEquals: { 'aws:SourceAccount': account },
          ArnLike: { 'aws:SourceArn': `arn:aws:bedrock-agentcore:${region}:${account}:*` },
        },
      }),
      description: `Execution role for AgentCore runtime ${agentName}`,
    });

    // Bedrock model invocation — covers foundation models, system-defined cross-region
    // inference profiles (e.g. global.anthropic.claude-sonnet-4-6), and account-owned profiles
    executionRole.addToPolicy(
      new PolicyStatement({
        effect: Effect.ALLOW,
        actions: ['bedrock:InvokeModel', 'bedrock:InvokeModelWithResponseStream'],
        resources: [
          `arn:aws:bedrock:*::foundation-model/*`,
          `arn:aws:bedrock:*::inference-profile/*`,
          `arn:aws:bedrock:*:${account}:inference-profile/*`,
        ],
      }),
    );

    // Grant X-Ray tracing permissions
    executionRole.addToPolicy(
      new PolicyStatement({
        effect: Effect.ALLOW,
        actions: [
          'xray:PutTraceSegments',
          'xray:PutTelemetryRecords',
          'xray:GetSamplingRules',
          'xray:GetSamplingTargets',
        ],
        resources: ['*'],
      }),
    );

    // Grant CloudWatch metrics permissions
    executionRole.addToPolicy(
      new PolicyStatement({
        effect: Effect.ALLOW,
        actions: ['cloudwatch:PutMetricData'],
        resources: ['*'],
        conditions: {
          StringEquals: {
            'cloudwatch:namespace': 'bedrock-agentcore',
          },
        },
      }),
    );

    // CloudWatch Logs — scoped to the AgentCore log group prefix
    executionRole.addToPolicy(
      new PolicyStatement({
        effect: Effect.ALLOW,
        actions: [
          'logs:CreateLogGroup',
          'logs:CreateLogStream',
          'logs:PutLogEvents',
          'logs:DescribeLogStreams',
          'logs:DescribeLogGroups',
        ],
        resources: [
          `arn:aws:logs:${region}:${account}:log-group:/aws/bedrock-agentcore/runtimes/*`,
          `arn:aws:logs:${region}:${account}:log-group:/aws/bedrock-agentcore/runtimes/*:log-stream:*`,
        ],
      }),
    );

    // ECR — GetAuthorizationToken is account-level and cannot be resource-scoped
    executionRole.addToPolicy(
      new PolicyStatement({
        sid: 'ECRAuthToken',
        effect: Effect.ALLOW,
        actions: ['ecr:GetAuthorizationToken'],
        resources: ['*'],
      }),
    );

    // ECR — image pull scoped to the asset repository and the CDK bootstrap repository pattern
    executionRole.addToPolicy(
      new PolicyStatement({
        sid: 'ECRImagePull',
        effect: Effect.ALLOW,
        actions: ['ecr:BatchGetImage', 'ecr:GetDownloadUrlForLayer', 'ecr:BatchCheckLayerAvailability'],
        resources: [
          imageAsset.repository.repositoryArn,
          `arn:aws:ecr:${region}:${account}:repository/cdk-*`,
        ],
      }),
    );

    // 3. AgentCore Runtime — L1 construct
    const runtimeName = `${projectName}_${agentName}`;
    const agentRuntime = new CfnRuntime(this, 'AgentRuntime', {
      agentRuntimeName: runtimeName,
      description: `AgentCore runtime for ${runtimeName}`,
      roleArn: executionRole.roleArn,
      agentRuntimeArtifact: {
        containerConfiguration: {
          containerUri: imageAsset.imageUri,
        },
      },
      networkConfiguration: {
        networkMode,
      },
    });

    // Ensure the role and all its policies exist before the Runtime is created
    agentRuntime.node.addDependency(executionRole);

    this.agentRuntimeId = agentRuntime.attrAgentRuntimeId;

    new CfnOutput(this, 'AgentRuntimeId', {
      description: 'AgentCore Runtime ID — use this to invoke the agent',
      value: agentRuntime.attrAgentRuntimeId,
    });

    new CfnOutput(this, 'AgentRuntimeArn', {
      description: 'AgentCore Runtime ARN',
      value: agentRuntime.attrAgentRuntimeArn,
    });

    new CfnOutput(this, 'StackNameOutput', {
      description: 'Name of the CloudFormation Stack',
      value: this.stackName,
    });
  }
}
