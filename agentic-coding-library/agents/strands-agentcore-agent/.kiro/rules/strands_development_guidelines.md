# Strands Agents Development Guidelines

## Purpose
Establish best practices for building AI agents using Strands framework to ensure maintainable, scalable, and efficient agent implementations.

## Instructions
- Use Strands SDK for rapid agent development with minimal code
- Define agent tools as separate Python functions with clear docstrings
- Implement proper error handling in all tool functions
- Use type hints for all function parameters and return values
- Keep agent logic focused and delegate complex operations to tools
- Use environment variables for configuration and API keys
- Implement proper logging for debugging and monitoring
- Test agents locally before deployment
- Use Flask or FastAPI for web-based agent interfaces
- Store agent state in JSON files or databases for persistence
- Follow Python naming conventions: snake_case for functions and variables

## Priority
High

## Error Handling
- If agent initialization fails, check model provider credentials and configuration
- For tool execution errors, provide clear error messages and fallback behavior
- If model responses are malformed, implement response validation and retry logic
- For API integration issues, verify endpoint URLs and authentication
- If state persistence fails, implement backup storage mechanisms
- For deployment errors, verify all dependencies are properly installed
