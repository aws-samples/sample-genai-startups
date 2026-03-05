import * as cdk from 'aws-cdk-lib';
import { Template } from 'aws-cdk-lib/assertions';
import { AgentCoreStack } from '../lib/cdk-stack';
import * as path from 'path';

test('AgentCoreStack synthesizes expected resources', () => {
  const app = new cdk.App();
  const stack = new AgentCoreStack(app, 'TestStack', {
    projectName: 'testproject',
    agentName: 'TestAgent',
    appDir: path.join(__dirname, '..', '..', '..', 'app', 'VercelAgent'),
    networkMode: 'PUBLIC',
    env: { account: '123456789012', region: 'us-east-1' },
  });
  const template = Template.fromStack(stack);

  template.hasOutput('StackNameOutput', {
    Description: 'Name of the CloudFormation Stack',
  });

  template.hasOutput('AgentRuntimeId', {
    Description: 'AgentCore Runtime ID — use this to invoke the agent',
  });

  template.hasResource('AWS::BedrockAgentCore::Runtime', {
    Properties: {
      AgentRuntimeName: 'testproject-TestAgent',
      NetworkConfiguration: { NetworkMode: 'PUBLIC' },
    },
  });

  template.hasResource('AWS::IAM::Role', {
    Properties: {
      AssumeRolePolicyDocument: {
        Statement: [
          {
            Principal: { Service: 'bedrock-agentcore.amazonaws.com' },
          },
        ],
      },
    },
  });
});