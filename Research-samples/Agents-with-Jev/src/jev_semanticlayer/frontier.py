from __future__ import annotations

import json
from dataclasses import dataclass
from time import perf_counter
from typing import TypeVar

from pydantic import BaseModel
from strands import Agent
from strands.models.openai import OpenAIModel

from jev_semanticlayer.config import Settings


OutputT = TypeVar("OutputT", bound=BaseModel)


@dataclass(frozen=True)
class FrontierResult:
    output: BaseModel
    input_tokens: int
    output_tokens: int
    latency_ms: float


class StrandsFrontierRunner:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def _model(
        self,
        output_model: type[OutputT] | None = None,
        *,
        max_completion_tokens: int | None = None,
        reasoning_effort: str | None = None,
    ) -> OpenAIModel:
        params = {
            "max_completion_tokens": (
                max_completion_tokens
                or self.settings.bedrock_max_completion_tokens
            ),
        }
        params["reasoning_effort"] = (
            reasoning_effort
            if reasoning_effort is not None
            else self.settings.bedrock_reasoning_effort
        )
        if output_model is not None:
            schema_name = output_model.__name__.lower()
            params["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": schema_name,
                    "strict": True,
                    "schema": output_model.model_json_schema(),
                },
            }
        session = self.settings.boto_session()
        return OpenAIModel(
            bedrock_mantle_config={
                "endpoint": self.settings.bedrock_endpoint,
                "region": self.settings.aws_region,
                "boto_session": session,
            },
            model_id=self.settings.bedrock_model_id,
            stream=False,
            params=params,
        )

    def chat_model(self) -> OpenAIModel:
        return self._model(
            max_completion_tokens=self.settings.agent_max_completion_tokens,
            reasoning_effort="none",
        )

    def run(
        self,
        *,
        output_model: type[OutputT],
        system_prompt: str,
        payload: dict,
    ) -> FrontierResult:
        agent = Agent(
            model=self._model(output_model),
            system_prompt=system_prompt,
            callback_handler=None,
        )
        started = perf_counter()
        result = agent(json.dumps(payload, sort_keys=True))
        elapsed_ms = (perf_counter() - started) * 1000

        parsed = output_model.model_validate_json(str(result).strip())
        usage = result.metrics.accumulated_usage
        return FrontierResult(
            output=parsed,
            input_tokens=int(usage.get("inputTokens", 0)),
            output_tokens=int(usage.get("outputTokens", 0)),
            latency_ms=elapsed_ms,
        )
