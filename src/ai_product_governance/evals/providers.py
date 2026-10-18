"""Model providers behind one small interface.

* `anthropic` - Claude through the official Anthropic SDK (adaptive thinking, effort,
  structured outputs, and server-side refusal fallbacks when configured).
* `openai` - OpenAI models through the official OpenAI SDK, plus any OpenAI-compatible
  endpoint via `base_url` (for example Gemini, Azure OpenAI, or a local model server).
* `claude-code` - Claude Code in headless mode with the user's Claude login: no API key
  (see claude_code.py).

The two API providers run the same manual tool loop so every model gets the same
skill-host tools; Claude Code loads the skill natively instead.
"""

from __future__ import annotations

import json
import os
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Protocol

from ai_product_governance.evals.config import ModelSpec

Executor = Callable[[str, dict[str, Any]], tuple[str, bool]]

ANTHROPIC_FALLBACK_BETA = "server-side-fallback-2026-07-01"


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    parameters: dict[str, Any]


@dataclass
class ToolCall:
    name: str
    arguments: dict[str, Any]
    output: str
    is_error: bool


@dataclass
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    reported_cost_usd: float | None = None  # set when the provider reports its own cost estimate

    def add(self, other: Usage) -> None:
        self.input_tokens += other.input_tokens
        self.output_tokens += other.output_tokens
        self.cache_read_tokens += other.cache_read_tokens
        if other.reported_cost_usd is not None:
            self.reported_cost_usd = (self.reported_cost_usd or 0.0) + other.reported_cost_usd

    def cost(self, price: dict[str, float] | None) -> float | None:
        if self.reported_cost_usd is not None:
            return self.reported_cost_usd
        if price is None:
            return None
        uncached = max(self.input_tokens - self.cache_read_tokens, 0)
        return (
            uncached * price["input"]
            + self.cache_read_tokens * price.get("cache_read", price["input"])
            + self.output_tokens * price["output"]
        ) / 1_000_000


@dataclass
class AgentResult:
    text: str
    tool_calls: list[ToolCall] = field(default_factory=list)
    usage: Usage = field(default_factory=Usage)
    turns: int = 0
    stop_reason: str = ""
    served_model: str = ""
    error: str | None = None


class Provider(Protocol):
    spec: ModelSpec

    def run_agent(
        self, system: str, user: str, tools: list[ToolSpec], execute: Executor, max_turns: int
    ) -> AgentResult: ...

    def complete_json(self, system: str, user: str, schema: dict[str, Any], schema_name: str) -> tuple[Any, Usage]: ...


class ProviderError(RuntimeError):
    """A provider call ended without a usable answer (refusal, truncation, malformed output)."""


class AnthropicProvider:
    def __init__(self, spec: ModelSpec) -> None:
        import anthropic

        params = spec.params
        kwargs: dict[str, Any] = {"max_retries": int(params.get("max_retries", 4))}
        key_env = params.get("api_key_env")
        if key_env:
            kwargs["api_key"] = os.environ.get(str(key_env))
        if params.get("base_url"):
            kwargs["base_url"] = params["base_url"]
        self.spec = spec
        self.client = anthropic.Anthropic(**kwargs)
        self.max_tokens = int(params.get("max_tokens", 16000))
        self.effort = params.get("effort")
        self.fallbacks = params.get("fallbacks")

    def _create(self, **request: Any) -> Any:
        if self.effort:
            request["output_config"] = {**request.get("output_config", {}), "effort": self.effort}
        if self.fallbacks:
            return self.client.beta.messages.create(
                betas=[ANTHROPIC_FALLBACK_BETA], fallbacks=self.fallbacks, **request
            )
        return self.client.messages.create(**request)

    @staticmethod
    def _usage(response: Any) -> Usage:
        usage = response.usage
        cache_read = getattr(usage, "cache_read_input_tokens", None) or 0
        cache_write = getattr(usage, "cache_creation_input_tokens", None) or 0
        return Usage(
            input_tokens=usage.input_tokens + cache_read + cache_write,
            output_tokens=usage.output_tokens,
            cache_read_tokens=cache_read,
        )

    @staticmethod
    def _text(response: Any) -> str:
        return "".join(block.text for block in response.content if block.type == "text")

    def run_agent(
        self, system: str, user: str, tools: list[ToolSpec], execute: Executor, max_turns: int
    ) -> AgentResult:
        messages: list[dict[str, Any]] = [{"role": "user", "content": user}]
        tool_params = [{"name": t.name, "description": t.description, "input_schema": t.parameters} for t in tools]
        result = AgentResult(text="")
        for turn in range(1, max_turns + 1):
            request: dict[str, Any] = {
                "model": self.spec.model,
                "max_tokens": self.max_tokens,
                "system": system,
                "messages": messages,
            }
            if tool_params:
                request["tools"] = tool_params
            response = self._create(**request)
            result.usage.add(self._usage(response))
            result.turns, result.stop_reason, result.served_model = turn, response.stop_reason, response.model
            if response.stop_reason == "refusal":
                details = getattr(response, "stop_details", None)
                result.error = f"refusal ({getattr(details, 'category', None) or 'unspecified'})"
                return result
            if response.stop_reason == "max_tokens":
                result.text, result.error = self._text(response), "truncated at max_tokens"
                return result
            tool_uses = [block for block in response.content if block.type == "tool_use"]
            if response.stop_reason in ("tool_use", "pause_turn"):
                # Append the full content unchanged: thinking and fallback blocks must round-trip.
                messages.append({"role": "assistant", "content": response.content})
                if tool_uses:
                    results = []
                    for block in tool_uses:
                        arguments = dict(block.input) if isinstance(block.input, dict) else {}
                        output, is_error = execute(block.name, arguments)
                        result.tool_calls.append(ToolCall(block.name, arguments, output, is_error))
                        entry: dict[str, Any] = {"type": "tool_result", "tool_use_id": block.id, "content": output}
                        if is_error:
                            entry["is_error"] = True
                        results.append(entry)
                    messages.append({"role": "user", "content": results})
                continue
            result.text = self._text(response)
            return result
        result.error = f"no final answer within {max_turns} turns"
        return result

    def complete_json(self, system: str, user: str, schema: dict[str, Any], schema_name: str) -> tuple[Any, Usage]:
        response = self._create(
            model=self.spec.model,
            max_tokens=self.max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
            output_config={"format": {"type": "json_schema", "schema": schema}},
        )
        if response.stop_reason in ("refusal", "max_tokens"):
            raise ProviderError(f"judge stopped with {response.stop_reason}")
        return json.loads(self._text(response)), self._usage(response)


class OpenAIProvider:
    def __init__(self, spec: ModelSpec) -> None:
        import openai

        params = spec.params
        key_env = str(params.get("api_key_env", "OPENAI_API_KEY"))
        kwargs: dict[str, Any] = {"api_key": os.environ.get(key_env), "max_retries": int(params.get("max_retries", 4))}
        if params.get("base_url"):
            kwargs["base_url"] = params["base_url"]
        self.spec = spec
        self.client = openai.OpenAI(**kwargs)
        self.token_param = str(params.get("token_param", "max_completion_tokens"))
        self.max_tokens = int(params.get("max_tokens", 16000))
        self.reasoning_effort = params.get("reasoning_effort")

    def _create(self, **request: Any) -> Any:
        request[self.token_param] = self.max_tokens
        if self.reasoning_effort:
            request["reasoning_effort"] = self.reasoning_effort
        return self.client.chat.completions.create(**request)

    @staticmethod
    def _usage(response: Any) -> Usage:
        usage = response.usage
        if usage is None:
            return Usage()
        details = getattr(usage, "prompt_tokens_details", None)
        cached = (getattr(details, "cached_tokens", None) or 0) if details else 0
        return Usage(input_tokens=usage.prompt_tokens, output_tokens=usage.completion_tokens, cache_read_tokens=cached)

    def run_agent(
        self, system: str, user: str, tools: list[ToolSpec], execute: Executor, max_turns: int
    ) -> AgentResult:
        messages: list[dict[str, Any]] = [{"role": "system", "content": system}, {"role": "user", "content": user}]
        tool_params = [
            {"type": "function", "function": {"name": t.name, "description": t.description, "parameters": t.parameters}}
            for t in tools
        ]
        result = AgentResult(text="")
        for turn in range(1, max_turns + 1):
            request: dict[str, Any] = {"model": self.spec.model, "messages": messages}
            if tool_params:
                request["tools"] = tool_params
            response = self._create(**request)
            result.usage.add(self._usage(response))
            choice = response.choices[0]
            message = choice.message
            result.turns, result.stop_reason, result.served_model = turn, choice.finish_reason, response.model
            calls = [c for c in (message.tool_calls or []) if getattr(c, "function", None) is not None]
            if calls:
                messages.append(
                    {
                        "role": "assistant",
                        "content": message.content or "",
                        "tool_calls": [
                            {
                                "id": c.id,
                                "type": "function",
                                "function": {"name": c.function.name, "arguments": c.function.arguments},
                            }
                            for c in calls
                        ],
                    }
                )
                for call in calls:
                    try:
                        arguments = json.loads(call.function.arguments or "{}")
                        output, is_error = execute(call.function.name, arguments if isinstance(arguments, dict) else {})
                    except json.JSONDecodeError:
                        arguments, output, is_error = {}, "Error: arguments were not valid JSON.", True
                    result.tool_calls.append(ToolCall(call.function.name, arguments, output, is_error))
                    messages.append({"role": "tool", "tool_call_id": call.id, "content": output})
                continue
            if getattr(message, "refusal", None):
                result.error = "refusal"
                return result
            result.text = message.content or ""
            if choice.finish_reason == "length":
                result.error = "truncated at max tokens"
            return result
        result.error = f"no final answer within {max_turns} turns"
        return result

    def complete_json(self, system: str, user: str, schema: dict[str, Any], schema_name: str) -> tuple[Any, Usage]:
        response = self._create(
            model=self.spec.model,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
            response_format={
                "type": "json_schema",
                "json_schema": {"name": schema_name, "schema": schema, "strict": True},
            },
        )
        message = response.choices[0].message
        if getattr(message, "refusal", None) or not message.content:
            raise ProviderError("judge returned no JSON content")
        return json.loads(message.content), self._usage(response)


def api_key_env(spec: ModelSpec) -> str:
    default = "ANTHROPIC_API_KEY" if spec.provider == "anthropic" else "OPENAI_API_KEY"
    return str(spec.params.get("api_key_env", default))


def readiness(spec: ModelSpec) -> tuple[bool, str]:
    """Best-effort check that a model can be called, with a hint for fixing it when it cannot."""
    if spec.provider == "claude-code":
        from ai_product_governance.evals.claude_code import ClaudeCodeProvider

        return ClaudeCodeProvider(spec).check_ready()
    if os.environ.get(api_key_env(spec)):
        return True, f"{api_key_env(spec)} is set"
    # The Anthropic SDK can also authenticate from ANTHROPIC_AUTH_TOKEN or an `ant auth login` profile.
    if (
        spec.provider == "anthropic"
        and "api_key_env" not in spec.params
        and (os.environ.get("ANTHROPIC_AUTH_TOKEN") or os.environ.get("ANTHROPIC_PROFILE"))
    ):
        return True, "Anthropic auth token or profile is set"
    return False, f"set {api_key_env(spec)}"


def credentials_available(spec: ModelSpec) -> bool:
    return readiness(spec)[0]


def create_provider(spec: ModelSpec) -> Provider:
    if spec.provider == "anthropic":
        return AnthropicProvider(spec)
    if spec.provider == "openai":
        return OpenAIProvider(spec)
    if spec.provider == "claude-code":
        from ai_product_governance.evals.claude_code import ClaudeCodeProvider

        return ClaudeCodeProvider(spec)
    raise ValueError(f"Unknown provider '{spec.provider}'")
