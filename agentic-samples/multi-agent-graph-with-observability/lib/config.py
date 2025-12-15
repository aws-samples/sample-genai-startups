"""
Configuration settings for the Insurance Claims Analysis System
"""

import os
from typing import Any, Dict

# Agent-specific model configurations
AGENT_MODEL_CONFIGS = {
    "document_analysis": {
        "provider": "bedrock",
        "model": "us.amazon.nova-pro-v1:0",  # Nova Pro for complex document analysis
        "temperature": 0.1,  # Low temperature for consistent document extraction
        "max_tokens": 10000,
        "streaming": True,
        "cache_prompt": None,
        "cache_tools": None,
    },
    "inspection": {
        "provider": "bedrock",
        "model": "us.amazon.nova-pro-v1:0",  # Nova Pro for complex inspection analysis
        "temperature": 0.1,  # Low temperature for consistent inspection analysis
        "max_tokens": 6000,
        "streaming": True,
        "cache_prompt": None,
        "cache_tools": None,
    },
    "policy_retrieval": {
        "provider": "bedrock",
        "model": "us.amazon.nova-lite-v1:0",
        "temperature": 0.1,  # Low temperature for consistent policy analysis
        "max_tokens": 3000,
        "streaming": True,
        "cache_prompt": None,
        "cache_tools": None,
    },
    "orchestrator": {
        "provider": "bedrock",
        "model": "us.amazon.nova-pro-v1:0",  # Nova Pro for complex orchestration
        "temperature": 0.2,  # Slightly higher for nuanced orchestration
        "max_tokens": 10000,
        "streaming": True,
        "cache_prompt": None,
        "cache_tools": None,
    },
    "claim_summary": {
        "provider": "bedrock",
        "model": "us.amazon.nova-lite-v1:0",  # Nova Lite for claim summaries
        "temperature": 0.1,  # Low temperature for consistent summaries
        "max_tokens": 6000,
        "streaming": True,
        "cache_prompt": None,
        "cache_tools": None,
    },
}

# Analysis thresholds for flagging
ANALYSIS_THRESHOLDS = {
    "damage_assessment_flag": 10000.0,
    "complex_case_flag": 50000.0,
    "executive_review_flag": 100000.0,
}

# Document analysis configuration
DOCUMENT_CONFIG = {
    "required_documents": {
        "auto": ["damage_photos", "police_report"],
        "home": ["damage_photos", "repair_estimates"],
        "theft": ["damage_photos", "police_report", "inventory_list"],
    },
    "max_file_size_mb": 50,
    "supported_formats": [".pdf", ".jpg", ".png", ".doc", ".docx"],
}


def get_config() -> Dict[str, Any]:
    """Get complete configuration dictionary"""
    return {
        "agents": AGENT_MODEL_CONFIGS,
        "analysis": ANALYSIS_THRESHOLDS,
        "documents": DOCUMENT_CONFIG,
    }


def get_agent_config(agent_name: str) -> Dict[str, Any]:
    """Get configuration for a specific agent"""
    return AGENT_MODEL_CONFIGS.get(agent_name, AGENT_MODEL_CONFIGS["document_analysis"])
