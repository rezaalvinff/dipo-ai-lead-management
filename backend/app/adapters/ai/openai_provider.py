"""OpenAI API provider (official SDK). Billed per token by OpenAI, separate from ChatGPT."""

import logging
import time

import openai

from app.adapters.ai.base import AgentOutput, AgentRequest, AIProviderError, AIResult
from app.adapters.ai.prompts import build_messages, build_system_prompt
from app.core.config import Settings

logger = logging.getLogger(__name__)


class OpenAIProvider:
    name = "openai"

    def __init__(self, settings: Settings, client: openai.AsyncOpenAI | None = None):
        self.model = settings.resolved_ai_model
        self._max_tokens = settings.ai_max_tokens
        self._client = client or openai.AsyncOpenAI(
            api_key=settings.openai_api_key,
            timeout=settings.ai_timeout_seconds,
            max_retries=2,
        )

    async def run_turn(self, request: AgentRequest) -> AIResult:
        messages = build_messages(request.history)
        if not messages:
            raise AIProviderError("No customer message to answer")
        started = time.perf_counter()
        try:
            completion = await self._client.chat.completions.parse(
                model=self.model,
                max_completion_tokens=self._max_tokens,
                messages=[{"role": "system", "content": build_system_prompt(request)}, *messages],
                response_format=AgentOutput,
            )
        except openai.APIStatusError as exc:
            raise AIProviderError(f"OpenAI API error {exc.status_code}: {exc.message}") from exc
        except openai.APIConnectionError as exc:
            raise AIProviderError(f"OpenAI connection error: {exc}") from exc

        latency_ms = int((time.perf_counter() - started) * 1000)
        choice = completion.choices[0]
        if getattr(choice.message, "refusal", None):
            raise AIProviderError("OpenAI refused the request", status="refusal")
        output = choice.message.parsed
        if output is None:
            raise AIProviderError(f"No structured output (finish_reason={choice.finish_reason})")
        usage = completion.usage
        return AIResult(
            output=output,
            provider=self.name,
            model=completion.model,
            input_tokens=usage.prompt_tokens if usage else None,
            output_tokens=usage.completion_tokens if usage else None,
            latency_ms=latency_ms,
        )
