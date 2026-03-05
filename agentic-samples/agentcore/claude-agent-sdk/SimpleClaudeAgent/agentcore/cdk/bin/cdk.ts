#!/usr/bin/env node
import * as fs from 'fs';
import * as path from 'path';
import { App } from 'aws-cdk-lib';
import { AgentCoreStack } from '../lib/cdk-stack';

// Config root is the parent of cdk/ (i.e. agentcore/)
const configRoot = path.resolve(process.cwd(), '..');

const agentcoreJson = JSON.parse(
  fs.readFileSync(path.join(configRoot, 'agentcore.json'), 'utf8'),
);
const awsTargets = JSON.parse(
  fs.readFileSync(path.join(configRoot, 'aws-targets.json'), 'utf8'),
);

const projectName: string = agentcoreJson.name;
// Takes the first agent — extend to a loop if you have multiple agents
const agent = agentcoreJson.agents[0];
const agentName: string = agent.name;
const appDir = path.resolve(configRoot, '..', agent.codeLocation);

const app = new App();

for (const target of awsTargets) {
  const stackName = `AgentCore-${projectName.replace(/_/g, '-')}-${(target.name as string).replace(/_/g, '-')}`;

  new AgentCoreStack(app, stackName, {
    projectName,
    agentName,
    appDir,
    networkMode: agent.networkMode ?? 'PUBLIC',
    env: { account: target.account, region: target.region },
    description: `AgentCore stack for ${projectName} (${target.region as string})`,
    tags: {
      'agentcore:project-name': projectName,
      'agentcore:target-name': target.name,
    },
  });
}

app.synth();
