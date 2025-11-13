"""LLM client for ReAct controller."""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional

from reasoning_service.config import settings

try:
    from openai import AsyncOpenAI
except ImportError:
    AsyncOpenAI = None

try:
    from anthropic import AsyncAnthropic
except ImportError:
    AsyncAnthropic = None


class LLMClientError(Exception):
    """Error raised by LLM client operations."""

    pass


class LLMClient:
    """Unified LLM client supporting multiple providers."""

    def __init__(
        self,
        provider: Optional[str] = None,
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
    ):
        """Initialize LLM client.

        Args:
            provider: LLM provider ("openai", "anthropic", or "vllm")
            model: Model name (e.g., "gpt-4o-mini", "claude-3-5-sonnet-20241022")
            temperature: Sampling temperature (0.0-2.0)
            max_tokens: Maximum tokens to generate
            api_key: API key (overrides config)
            base_url: Base URL for vLLM or custom endpoints
        """
        self.provider = provider or settings.llm_provider
        self.model = model or settings.llm_model
        self.temperature = temperature if temperature is not None else settings.controller_temperature
        self.max_tokens = max_tokens or 2000

        # Get API key from parameter, environment, or config
        api_key = api_key or os.getenv("LLM_API_KEY") or settings.llm_api_key
        base_url = base_url or os.getenv("LLM_BASE_URL") or settings.llm_base_url

        if self.provider == "openai":
            if AsyncOpenAI is None:
                raise LLMClientError("openai package not installed. Install with: pip install openai")
            self.client = AsyncOpenAI(api_key=api_key or os.getenv("OPENAI_API_KEY"))
        elif self.provider == "anthropic":
            if AsyncAnthropic is None:
                raise LLMClientError("anthropic package not installed. Install with: pip install anthropic")
            self.client = AsyncAnthropic(api_key=api_key or os.getenv("ANTHROPIC_API_KEY"))
        elif self.provider == "vllm":
            if AsyncOpenAI is None:
                raise LLMClientError("openai package not installed. Install with: pip install openai")
            vllm_url = base_url or os.getenv("VLLM_BASE_URL", "http://localhost:8000/v1")
            self.client = AsyncOpenAI(base_url=vllm_url, api_key=api_key or "EMPTY")
        else:
            raise LLMClientError(f"Unknown provider: {self.provider}")

    async def call_with_tools(
        self,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
        tool_choice: str = "auto",
    ) -> Dict[str, Any]:
        """Call LLM with function calling.

        Args:
            messages: List of message dictionaries (system, user, assistant, tool)
            tools: List of tool definitions in OpenAI function calling format
            tool_choice: Tool choice strategy ("auto", "required", "none", or tool name)

        Returns:
            Dictionary with:
                - role: "assistant"
                - content: Text content (may be None if only tool calls)
                - tool_calls: List of tool call objects
                - finish_reason: Reason for completion ("stop", "tool_calls", etc.)
        """
        if self.provider in ["openai", "vllm"]:
            return await self._call_openai(messages, tools, tool_choice)
        elif self.provider == "anthropic":
            return await self._call_anthropic(messages, tools, tool_choice)
        else:
            raise LLMClientError(f"Provider {self.provider} not supported")

    async def _call_openai(
        self,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
        tool_choice: str,
    ) -> Dict[str, Any]:
        """Call OpenAI-compatible API."""
        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                tools=tools if tools else None,
                tool_choice=tool_choice if tools else None,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
            )

            choice = response.choices[0]
            message = choice.message

            # Parse tool calls
            tool_calls = []
            if message.tool_calls:
                for tc in message.tool_calls:
                    tool_calls.append({
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        },
                    })

            return {
                "role": message.role or "assistant",
                "content": message.content,
                "tool_calls": tool_calls,
                "finish_reason": choice.finish_reason,
            }
        except Exception as e:
            raise LLMClientError(f"OpenAI API call failed: {str(e)}") from e

    async def _call_anthropic(
        self,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
        tool_choice: str,
    ) -> Dict[str, Any]:
        """Call Anthropic Messages API."""
        try:
            # Convert messages format for Anthropic
            anthropic_messages = []
            for msg in messages:
                if msg["role"] == "system":
                    continue  # Anthropic uses separate system parameter
                elif msg["role"] == "tool":
                    # Anthropic uses "tool_result" role
                    anthropic_messages.append({
                        "role": "user",
                        "content": [{
                            "type": "tool_result",
                            "tool_use_id": msg.get("tool_call_id", ""),
                            "content": msg.get("content", ""),
                        }],
                    })
                else:
                    anthropic_messages.append(msg)

            # Extract system message
            system_messages = [msg["content"] for msg in messages if msg["role"] == "system"]
            system = "\n".join(system_messages) if system_messages else None

            # Convert tools format
            anthropic_tools = []
            for tool in tools:
                if tool.get("type") == "function":
                    anthropic_tools.append({
                        "name": tool["function"]["name"],
                        "description": tool["function"]["description"],
                        "input_schema": tool["function"]["parameters"],
                    })

            response = await self.client.messages.create(
                model=self.model,
                messages=anthropic_messages,
                system=system,
                tools=anthropic_tools if anthropic_tools else None,
                tool_choice="auto" if tool_choice == "auto" else None,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
            )

            # Parse response
            tool_calls = []
            content_text = None

            for content_block in response.content:
                if content_block.type == "text":
                    content_text = content_block.text
                elif content_block.type == "tool_use":
                    # Anthropic returns input as dict, convert to JSON string
                    arguments = json.dumps(content_block.input) if isinstance(content_block.input, dict) else str(content_block.input)
                    tool_calls.append({
                        "id": content_block.id,
                        "type": "function",
                        "function": {
                            "name": content_block.name,
                            "arguments": arguments,
                        },
                    })

            return {
                "role": "assistant",
                "content": content_text,
                "tool_calls": tool_calls,
                "finish_reason": response.stop_reason,
            }
        except Exception as e:
            raise LLMClientError(f"Anthropic API call failed: {str(e)}") from e

