"""Claude via the Anthropic API (official SDK).

Billing: this uses an Anthropic API key from console.anthropic.com, charged per
token. It is NOT related to a Claude Pro subscription.
"""

import logging
import time

import anthropic

from app.adapters.ai.base import AgentOutput, AgentRequest, AIProviderError, AIResult
from app.adapters.ai.prompts import build_messages, build_system_prompt
from app.core.config import Settings

logger = logging.getLogger(__name__)

FALLBACK_BETA = "server-side-fallback-2026-07-01"


class AnthropicProvider:
    name = "anthropic"

    def __init__(self, settings: Settings, client: anthropic.AsyncAnthropic | None = None):
        self.model = settings.resolved_ai_model
        self._effort = settings.ai_effort
        self._max_tokens = settings.ai_max_tokens
        self._client = client or anthropic.AsyncAnthropic(
            api_key=settings.anthropic_api_key,
            timeout=settings.ai_timeout_seconds,
            max_retries=2,
        )

    async def run_turn(self, request: AgentRequest) -> AIResult:
        messages = build_messages(request.history)
        if not messages:
            raise AIProviderError("No customer message to answer")
        started = time.perf_counter()
        try:
            response = await self._client.beta.messages.parse(
                model=self.model,
                max_tokens=self._max_tokens,
                system=build_system_prompt(request),
                messages=messages,
                output_format=AgentOutput,
                output_config={"effort": self._effort},
                # If a safety classifier declines, the API retries on a fallback model.
                betas=[FALLBACK_BETA],
                fallbacks="default",
            )
        except anthropic.RateLimitError as exc:
            raise AIProviderError(f"Anthropic rate limit: {exc.message}") from exc
        except anthropic.APIStatusError as exc:
            raise AIProviderError(f"Anthropic API error {exc.status_code}: {exc.message}") from exc
        except anthropic.APIConnectionError as exc:
            raise AIProviderError(f"Anthropic connection error: {exc}") from exc

        latency_ms = int((time.perf_counter() - started) * 1000)
        if response.stop_reason == "refusal":
            raise AIProviderError("Anthropic refused the request", status="refusal")
        output = response.parsed_output
        if output is None:
            raise AIProviderError(f"No structured output (stop_reason={response.stop_reason})")
        return AIResult(
            output=output,
            provider=self.name,
            model=response.model,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            latency_ms=latency_ms,
        )
