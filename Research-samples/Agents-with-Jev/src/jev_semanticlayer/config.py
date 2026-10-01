from __future__ import annotations

import os
from dataclasses import dataclass
from decimal import Decimal

import boto3
from dotenv import load_dotenv


def _optional(name: str) -> str | None:
    value = os.getenv(name, "").strip()
    return value or None


@dataclass(frozen=True)
class Settings:
    aws_region: str
    aws_profile: str | None
    bedrock_model_id: str
    bedrock_endpoint: str
    bedrock_max_completion_tokens: int
    bedrock_reasoning_effort: str
    bedrock_input_usd_per_million: Decimal
    bedrock_output_usd_per_million: Decimal
    typesafe_api_key: str | None
    jev_model: str
    jev_input_usd_per_million: Decimal
    jev_output_usd_per_million: Decimal
    review_confidence_threshold: float
    semantic_state_table: str
    agent_max_completion_tokens: int

    @classmethod
    def from_env(cls) -> "Settings":
        load_dotenv()
        return cls(
            aws_region=os.getenv("AWS_REGION", "us-east-1"),
            aws_profile=_optional("AWS_PROFILE"),
            bedrock_model_id=os.getenv(
                "BEDROCK_MODEL_ID", "global.openai.gpt-5.6-sol"
            ),
            bedrock_endpoint=os.getenv("BEDROCK_ENDPOINT", "bedrock-runtime"),
            bedrock_max_completion_tokens=int(
                os.getenv("BEDROCK_MAX_COMPLETION_TOKENS", "1200")
            ),
            bedrock_reasoning_effort=os.getenv(
                "BEDROCK_REASONING_EFFORT", "medium"
            ),
            bedrock_input_usd_per_million=Decimal(
                os.getenv("BEDROCK_INPUT_USD_PER_MILLION", "4.00")
            ),
            bedrock_output_usd_per_million=Decimal(
                os.getenv("BEDROCK_OUTPUT_USD_PER_MILLION", "20.00")
            ),
            typesafe_api_key=_optional("TYPESAFE_API_KEY"),
            jev_model=os.getenv("TYPESAFE_DEFAULT_MODEL", "jev-latest"),
            jev_input_usd_per_million=Decimal(
                os.getenv("JEV_INPUT_USD_PER_MILLION", "0.042")
            ),
            jev_output_usd_per_million=Decimal(
                os.getenv("JEV_OUTPUT_USD_PER_MILLION", "0")
            ),
            review_confidence_threshold=float(
                os.getenv("REVIEW_CONFIDENCE_THRESHOLD", "0.65")
            ),
            semantic_state_table=os.getenv(
                "SEMANTIC_STATE_TABLE", "jev-semantic-state"
            ),
            agent_max_completion_tokens=int(
                os.getenv("AGENT_MAX_COMPLETION_TOKENS", "1200")
            ),
        )

    def boto_session(self) -> boto3.Session:
        if self.aws_profile:
            return boto3.Session(
                profile_name=self.aws_profile,
                region_name=self.aws_region,
            )
        return boto3.Session(region_name=self.aws_region)
