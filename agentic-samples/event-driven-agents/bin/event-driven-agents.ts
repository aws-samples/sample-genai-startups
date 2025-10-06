#!/usr/bin/env node
import * as cdk from 'aws-cdk-lib';
import { Aspects } from 'aws-cdk-lib';
import { AwsSolutionsChecks } from 'cdk-nag'
import { EventDrivenAgentsStack } from '../lib/event-driven-agents-stack';

const app = new cdk.App();
Aspects.of(app).add(new AwsSolutionsChecks({ verbose: true }))
new EventDrivenAgentsStack(app, 'EventDrivenAgentsStack', {
  env: { region: 'us-west-2' }
});