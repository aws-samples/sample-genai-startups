"""
Configuration Management for Solar Agent

This module handles all configuration settings for the solar agent,
including AWS services, Langfuse observability, and Strands framework settings.
"""

import os
from typing import Dict, Any, Optional
from dataclasses import dataclass
from dotenv import load_dotenv
import sys

# Load environment variables
load_dotenv()

@dataclass
class AWSConfig:
    """AWS service configuration."""
    region: str
    dynamodb_table: str
    dynamodb_pk: str
    dynamodb_sk: str
    bedrock_knowledge_base_id: Optional[str] = None
    
    @classmethod
    def from_env(cls) -> 'AWSConfig':
        """Create AWS config from environment variables."""
        return cls(
            region=os.getenv('AWS_REGION', 'us-east-1'),
            dynamodb_table=os.getenv('DYNAMODB_TABLE', ''),
            dynamodb_pk=os.getenv('DYNAMODB_PK', 'customer_id'),
            dynamodb_sk=os.getenv('DYNAMODB_SK', 'ticket_id'),
            bedrock_knowledge_base_id=os.getenv('BEDROCK_KNOWLEDGE_BASE_ID')
        )
    
    def validate(self) -> bool:
        """Validate that required AWS configuration is present."""
        required_fields = ['region', 'dynamodb_table']
        for field in required_fields:
            if not getattr(self, field):
                raise ValueError(f"Missing required AWS configuration: {field}")
        return True

@dataclass
class LangfuseConfig:
    """Langfuse observability configuration."""
    public_key: str
    secret_key: str
    host: str
    environment: str
    debug: bool = False
    
    @classmethod
    def from_env(cls) -> 'LangfuseConfig':
        """Create Langfuse config from environment variables."""
        return cls(
            public_key=os.getenv('LANGFUSE_PUBLIC_KEY', ''),
            secret_key=os.getenv('LANGFUSE_SECRET_KEY', ''),
            host=os.getenv('LANGFUSE_HOST', 'https://cloud.langfuse.com'),
            environment=os.getenv('LANGFUSE_ENVIRONMENT', 'development'),
            debug=os.getenv('LANGFUSE_DEBUG', 'false').lower() == 'true'
        )
    
    def validate(self) -> bool:
        """Validate that required Langfuse configuration is present."""
        required_fields = ['public_key', 'secret_key']
        for field in required_fields:
            if not getattr(self, field):
                raise ValueError(f"Missing required Langfuse configuration: {field}")
        return True

@dataclass
class StrandsConfig:
    """Strands framework configuration."""
    model: str
    environment: str
    max_retries: int = 3
    timeout: int = 30
    
    @classmethod
    def from_env(cls) -> 'StrandsConfig':
        """Create Strands config from environment variables."""
        return cls(
            model=os.getenv('STRANDS_MODEL', 'us.anthropic.claude-3-7-sonnet-20250219-v1:0'),
            environment=os.getenv('STRANDS_ENVIRONMENT', 'development'),
            max_retries=int(os.getenv('STRANDS_MAX_RETRIES', '3')),
            timeout=int(os.getenv('STRANDS_TIMEOUT', '30'))
        )

@dataclass
class AgentConfig:
    """Complete agent configuration."""
    aws: AWSConfig
    langfuse: LangfuseConfig
    strands: StrandsConfig
    
    @classmethod
    def from_env(cls) -> 'AgentConfig':
        """Create complete agent config from environment variables."""
        return cls(
            aws=AWSConfig.from_env(),
            langfuse=LangfuseConfig.from_env(),
            strands=StrandsConfig.from_env()
        )
    
    def validate(self) -> bool:
        """Validate all configuration sections."""
        self.aws.validate()
        self.langfuse.validate()
        return True
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert configuration to dictionary for logging/debugging."""
        return {
            'aws': {
                'region': self.aws.region,
                'dynamodb_table': self.aws.dynamodb_table,
                'has_knowledge_base': bool(self.aws.bedrock_knowledge_base_id)
            },
            'langfuse': {
                'host': self.langfuse.host,
                'environment': self.langfuse.environment,
                'debug': self.langfuse.debug
            },
            'strands': {
                'model': self.strands.model,
                'environment': self.strands.environment,
                'max_retries': self.strands.max_retries,
                'timeout': self.strands.timeout
            }
        }

# Global configuration instance
config = AgentConfig.from_env()

def get_config() -> AgentConfig:
    """Get the global configuration instance."""
    return config

def validate_config() -> bool:
    """Validate the global configuration."""
    try:
        config.validate()
        return True
    except ValueError as e:
        print(f"Configuration validation failed: {e}")
        return False

def print_config_summary():
    """Print a summary of the current configuration."""
    print("🔧 Solar Agent Configuration Summary")
    print("=" * 50)
    
    config_dict = config.to_dict()
    
    print(f"AWS Region: {config_dict['aws']['region']}")
    print(f"DynamoDB Table: {config_dict['aws']['dynamodb_table']}")
    print(f"Knowledge Base Configured: {config_dict['aws']['has_knowledge_base']}")
    print()
    print(f"Langfuse Host: {config_dict['langfuse']['host']}")
    print(f"Langfuse Environment: {config_dict['langfuse']['environment']}")
    print(f"Debug Mode: {config_dict['langfuse']['debug']}")
    print()
    print(f"Strands Model: {config_dict['strands']['model']}")
    print(f"Strands Environment: {config_dict['strands']['environment']}")
    print(f"Max Retries: {config_dict['strands']['max_retries']}")
    print(f"Timeout: {config_dict['strands']['timeout']}s")
    print("=" * 50)

if __name__ == "__main__":
    # Test configuration loading and validation
    print_config_summary()
    
    if validate_config():
        print("✅ Configuration is valid!")
    else:
        print("❌ Configuration validation failed!")
        sys.exit(1)
