"""Token Factory adapter for the `LLM` port: routing, retries, fallback, schema repair,
per-model concurrency, budgets, trace and the exact-repeat cache (SPEC "LLM gateway")."""

import asyncio
import re
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

import openai
import structlog
from openai import AsyncOpenAI
from pydantic import BaseModel, SecretStr, ValidationError

from greenink.core.enums import ErrorCode, LLMCallStatus, LLMTask
from greenink.core.errors import GreenInkError
from greenink.core.ids import new_id
from greenink.core.models import LLMCall
from greenink.llm.messages import Message, build_messages, prompt_hash, response_format
from greenink.llm.port import LLMInput, LLMResult
from greenink.llm.pricing import cost_usd
from greenink.llm.router import ModelsConfig, TaskRoute
from greenink.llm.trace import TraceStore

log = structlog.get_logger()

PRIMARY_ATTEMPTS = 3
"""First try plus two retries on the primary model, then the fallback (SPEC)."""
BACKOFF_S = 0.5
_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$")
_THINK = re.compile(r"<think>.*?</think>", re.DOTALL)


class _RetryableError(Exception):
    """Timeout, rate limit, 5xx or connection error: worth another attempt."""


@dataclass
class _Usage:
    tokens_in: int = 0
    tokens_out: int = 0
    cost: float = 0.0

    def add(self, config: ModelsConfig, model: str, tokens_in: int, tokens_out: int) -> None:
        self.tokens_in += tokens_in
        self.tokens_out += tokens_out
        self.cost += cost_usd(config.pricing_usd_per_1m[model], tokens_in, tokens_out)


def make_client(config: ModelsConfig, api_key: SecretStr) -> AsyncOpenAI:
    # Retries are ours (they include the fallback model), so the SDK's are off.
    return AsyncOpenAI(
        base_url=str(config.provider.base_url), api_key=api_key.get_secret_value(), max_retries=0
    )


class TokenFactoryGateway:
    def __init__(
        self,
        config: ModelsConfig,
        client: AsyncOpenAI,
        trace: TraceStore,
        *,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self._config = config
        self._client = client
        self._trace = trace
        self._sleep = sleep
        self._semaphores = {model: asyncio.Semaphore(config.concurrency(model)) for model in config.models()}

    async def run[T: BaseModel](
        self,
        task: LLMTask,
        input: LLMInput,
        schema: type[T],
        *,
        analysis_id: UUID | None = None,
    ) -> LLMResult[T]:
        route = self._config.route(task)
        messages = build_messages(input)
        key = prompt_hash(task, route.model, messages, schema)

        cached = await self._trace.find_cached(key)
        if cached is not None:
            try:
                output = schema.model_validate(cached)
            except ValidationError:
                log.warning("llm_cache_invalid", task=task, prompt_hash=key)
            else:
                call = self._call(task, route.model, key, analysis_id, _Usage(), 0, LLMCallStatus.CACHED)
                await self._trace.record(call, None)
                return self._result(output, call, cached=True)

        await self._check_budget(task, route.model, key, analysis_id)

        started = time.monotonic()
        usage = _Usage()
        try:
            model, output = await self._answer(task, route, messages, schema, usage)
        except GreenInkError as exc:
            status = LLMCallStatus.INVALID_OUTPUT if exc.code == ErrorCode.INTERNAL else LLMCallStatus.ERROR
            call = self._call(task, route.model, key, analysis_id, usage, _ms(started), status)
            await self._trace.record(call, None, exc.message)
            raise

        call = self._call(task, model, key, analysis_id, usage, _ms(started), LLMCallStatus.OK)
        await self._trace.record(call, output.model_dump(mode="json"))
        log.info(
            "llm_call",
            task=task,
            model=model,
            tokens_in=usage.tokens_in,
            tokens_out=usage.tokens_out,
            cost_usd=round(usage.cost, 6),
            latency_ms=call.latency_ms,
        )
        return self._result(output, call, cached=False)

    async def _check_budget(self, task: LLMTask, model: str, key: str, analysis_id: UUID | None) -> None:
        budgets = self._config.budgets
        reason = None
        if await self._trace.spent_today_usd() >= budgets.daily_usd:
            reason = "The daily model budget is used up. Cached reports still open; try again tomorrow."
        elif (
            analysis_id and await self._trace.spent_for_analysis_usd(analysis_id) >= budgets.per_analysis_usd
        ):
            reason = "This report reached its model budget; it shows the results found so far."
        if reason:
            call = self._call(task, model, key, analysis_id, _Usage(), 0, LLMCallStatus.BUDGET_EXCEEDED)
            await self._trace.record(call, None, reason)
            raise GreenInkError(ErrorCode.BUDGET_EXCEEDED, reason, retryable=False)

    async def _answer[T: BaseModel](
        self, task: LLMTask, route: TaskRoute, messages: list[Message], schema: type[T], usage: _Usage
    ) -> tuple[str, T]:
        """Primary model with retries, then the fallback; one repair call on invalid JSON."""
        candidates = [route.model] * PRIMARY_ATTEMPTS + ([route.fallback] if route.fallback else [])
        last_error = "no attempt made"
        for attempt, model in enumerate(candidates):
            if attempt:
                await self._sleep(BACKOFF_S * 2 ** min(attempt - 1, 3))
            try:
                text = await self._complete(route, model, messages, schema, usage)
            except _RetryableError as exc:
                last_error = str(exc)
                log.warning("llm_retry", task=task, model=model, attempt=attempt + 1, error=last_error)
                continue
            try:
                return model, _parse(text, schema)
            except ValidationError as exc:
                repaired = await self._repair(route, model, messages, text, exc, schema, usage)
                if repaired is not None:
                    return model, repaired
                raise GreenInkError(
                    ErrorCode.INTERNAL, f"The {task} model returned output that failed validation twice."
                ) from None
        raise GreenInkError(
            ErrorCode.UPSTREAM_UNAVAILABLE,
            f"The model service did not answer the {task} step ({last_error}). Please retry.",
        )

    async def _repair[T: BaseModel](
        self,
        route: TaskRoute,
        model: str,
        messages: list[Message],
        bad: str,
        error: ValidationError,
        schema: type[T],
        usage: _Usage,
    ) -> T | None:
        problems = "; ".join(
            f"{'.'.join(str(p) for p in e['loc']) or '(root)'}: {e['msg']}" for e in error.errors()[:20]
        )
        repair = [
            *messages,
            {"role": "assistant", "content": bad[:20_000]},
            {
                "role": "user",
                "content": f"That JSON failed validation: {problems}. Reply with corrected JSON only.",
            },
        ]
        try:
            text = await self._complete(route, model, repair, schema, usage)
            return _parse(text, schema)
        except (_RetryableError, ValidationError):
            return None

    async def _complete(
        self, route: TaskRoute, model: str, messages: list[Message], schema: type[BaseModel], usage: _Usage
    ) -> str:
        async with self._semaphores[model]:
            try:
                response = await asyncio.wait_for(
                    self._client.chat.completions.create(  # type: ignore[call-overload]
                        model=model,
                        messages=messages,
                        max_tokens=route.max_output_tokens,
                        temperature=0,
                        response_format=response_format(schema),
                        extra_body={"chat_template_kwargs": {"enable_thinking": route.thinking}},
                    ),
                    timeout=route.timeout_s,
                )
            except TimeoutError:
                raise _RetryableError(f"timeout after {route.timeout_s:g}s") from None
            except openai.APIStatusError as exc:
                if exc.status_code == 429 or exc.status_code >= 500:
                    raise _RetryableError(f"HTTP {exc.status_code}") from None
                raise GreenInkError(
                    ErrorCode.UPSTREAM_UNAVAILABLE,
                    f"The model service rejected the request (HTTP {exc.status_code}).",
                    retryable=False,
                ) from None
            except (openai.APIConnectionError, openai.APITimeoutError):
                raise _RetryableError("connection error") from None
        if response.usage:
            usage.add(self._config, model, response.usage.prompt_tokens, response.usage.completion_tokens)
        choice = response.choices[0]
        if choice.finish_reason == "length" and not choice.message.content:
            raise _RetryableError(f"no answer within {route.max_output_tokens} output tokens")
        return choice.message.content or ""

    def _call(
        self,
        task: LLMTask,
        model: str,
        key: str,
        analysis_id: UUID | None,
        usage: _Usage,
        latency_ms: int,
        status: LLMCallStatus,
    ) -> LLMCall:
        return LLMCall(
            id=new_id(),
            analysis_id=analysis_id,
            task=task,
            model=model,
            tokens_in=usage.tokens_in,
            tokens_out=usage.tokens_out,
            cost_usd=usage.cost,
            latency_ms=latency_ms,
            status=status,
            prompt_hash=key,
            created_at=datetime.now(UTC),
        )

    @staticmethod
    def _result[T: BaseModel](output: T, call: LLMCall, *, cached: bool) -> LLMResult[T]:
        return LLMResult(
            output=output,
            call_id=call.id,
            model=call.model,
            tokens_in=call.tokens_in,
            tokens_out=call.tokens_out,
            cost_usd=call.cost_usd,
            latency_ms=call.latency_ms,
            cached=cached,
        )


def _parse[T: BaseModel](text: str, schema: type[T]) -> T:
    """Strip stray reasoning tags and code fences, then validate. Raises ValidationError."""
    cleaned = _FENCE.sub("", _THINK.sub("", text).strip()).strip()
    return schema.model_validate_json(cleaned)


def _ms(started: float) -> int:
    return int((time.monotonic() - started) * 1000)
