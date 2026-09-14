# Amazon Bedrock AgentCore Evaluations - Tutorial

A hands-on tutorial for **Amazon Bedrock AgentCore Evaluations**, the AWS managed service that automatically assesses the quality and performance of your AI agents using LLM-as-a-Judge techniques.

## What You'll Learn

- How AgentCore Evaluations works (trace-based evaluation with OpenTelemetry)
- How to deploy a Strands agent on AgentCore Runtime with observability
- How to use **built-in evaluators** (GoalSuccessRate, Correctness, ToolSelectionAccuracy, ToolParameterAccuracy)
- How to create **custom evaluators** with your own scoring criteria
- How to run **on-demand evaluations** for development and troubleshooting
- How to set up **online evaluations** for continuous production monitoring

## Prerequisites

- An AWS account with access to Amazon Bedrock AgentCore
- Python 3.10+
- AWS credentials configured (`aws configure`)
- Jupyter Notebook or JupyterLab

## Getting Started

1. Clone this repository:

```bash
git clone https://gitlab.aws.dev/ndeplace/agentcore-evaluation.git
cd agentcore-evaluation
```

2. Install dependencies:

```bash
pip install boto3 botocore bedrock-agentcore-starter-toolkit
pip install opentelemetry-api opentelemetry-sdk aws-opentelemetry-distro
```

3. Open the notebook:

```bash
jupyter notebook 02_agentcoreEvaluation2.ipynb
```

## Notebook Structure

| Section | Description |
|---------|-------------|
| **1. Introduction** | Overview of the service and its capabilities |
| **2. What is AgentCore Evaluations?** | Architecture diagram and key components |
| **3. Key Concepts** | Traces, spans, sessions, evaluators, configurations |
| **4. Prerequisites & Setup** | Install dependencies, (optional) deploy a Strands agent, configure SDK |
| **5. Architecture** | Evaluation flow and LLM-as-a-Judge pattern |
| **6. Built-in Evaluators** | List available evaluators and run them on a session |
| **7. Custom Evaluators** | Create a custom evaluator with your own rating scale |
| **8. On-Demand Evaluations** | Evaluate specific sessions synchronously |
| **9. Online Evaluations** | Set up continuous evaluation in production |
| **10. Best Practices** | Sampling strategies, cost optimization, workflow integration |

## Key Dependencies

| Package | Purpose |
|---------|---------|
| `boto3` | AWS SDK |
| `bedrock-agentcore-starter-toolkit` | AgentCore evaluation and deployment toolkit |
| `strands-agents` | Strands agent framework (optional, for agent deployment) |
| `strands-agents-tools` | Built-in tools for Strands agents (optional) |
| `aws-opentelemetry-distro` | OpenTelemetry instrumentation |

## Resources

- [AgentCore Evaluations Documentation](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/evaluations.html)
- [AgentCore Samples Repository](https://github.com/awslabs/amazon-bedrock-agentcore-samples/tree/main/01-tutorials/07-AgentCore-evaluations)
- [Bedrock AgentCore API Reference](https://docs.aws.amazon.com/bedrock-agentcore/latest/APIReference/)
