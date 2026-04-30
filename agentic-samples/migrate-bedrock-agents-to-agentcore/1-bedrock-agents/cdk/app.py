#!/usr/bin/env python3
import aws_cdk as cdk
from stacks.bedrock_agent_stack import BedrockAgentStack

app = cdk.App()
BedrockAgentStack(app, "PrivateAviationAgentStack",
    env=cdk.Environment(region="us-east-1"),
)
app.synth()
