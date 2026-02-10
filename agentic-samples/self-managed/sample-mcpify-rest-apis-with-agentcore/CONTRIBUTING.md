# Contributing to Sample: MCPifying APIs with Amazon Bedrock AgentCore Gateway

We welcome contributions to this AWS sample! This document provides guidelines for contributing to the project.

## How to Contribute

### Reporting Issues

If you encounter any issues with the sample:

1. Check existing issues to see if the problem has already been reported
2. Create a new issue with:
   - Clear description of the problem
   - Steps to reproduce the issue
   - Expected vs actual behavior
   - Environment details (AWS region, versions, etc.)
   - Relevant logs or error messages

### Suggesting Enhancements

We welcome suggestions for improvements:

1. Check existing issues and pull requests for similar suggestions
2. Create an issue describing:
   - The enhancement you'd like to see
   - Why it would be valuable
   - How it might be implemented

### Submitting Pull Requests

1. Fork the repository
2. Create a feature branch from `main`
3. Make your changes following the guidelines below
4. Test your changes thoroughly
5. Submit a pull request with:
   - Clear description of changes
   - Reference to related issues
   - Testing performed

## Development Guidelines

### Code Style

- **Python**: Follow PEP 8 style guidelines
- **Shell Scripts**: Use shellcheck for validation
- **YAML/JSON**: Maintain consistent indentation (2 spaces)
- **Documentation**: Use clear, concise language

### Testing

Before submitting changes:

1. Test deployment scripts in a clean AWS environment
2. Verify all configuration examples work as documented
3. Test the complete MCPification flow
4. Ensure cleanup scripts work properly

### Documentation

- Update README.md for any functional changes
- Include inline comments for complex logic
- Update configuration examples if needed
- Ensure all placeholders are clearly marked

### Security

- Never commit real AWS credentials or secrets
- Use placeholder values in all examples
- Follow AWS security best practices
- Document security considerations for any changes

## Sample Structure

```
sample-mcpify-api-with-agentcore-gateway/
├── app/                    # Flask retail application
├── k8s/                    # Kubernetes manifests
├── terraform/              # EKS infrastructure
├── scripts/                # Build and deployment scripts
├── agentcore-integration/  # AgentCore Gateway deployment
├── README.md              # Main documentation
├── CONTRIBUTING.md        # This file
└── LICENSE                # MIT No Attribution license
```

## Review Process

All contributions will be reviewed for:

- Functionality and correctness
- Security best practices
- Documentation quality
- Consistency with existing code
- AWS service usage patterns

## Questions?

If you have questions about contributing, please:

1. Check the existing documentation
2. Search existing issues
3. Create a new issue with your question

Thank you for contributing to this AWS sample!