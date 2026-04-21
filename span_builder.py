from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

from openinference.semconv.trace import OpenInferenceSpanKindValues, SpanAttributes

from .payload_sanitizer import sanitize_string, sanitize_value

logger = logging.getLogger("hermes-phoenix-otel")

_SPAN_KIND_AGENT = OpenInferenceSpanKindValues.AGENT.value
_SPAN_KIND_LLM = OpenInferenceSpanKindValues.LLM.value
_SPAN_KIND_TOOL = OpenInferenceSpanKindValues.TOOL.value

SA = SpanAttributes


def _try_parse_json(value: Any) -> Any:
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            if isinstance(parsed, (dict, list)):
                return parsed
        except (json.JSONDecodeError, TypeError):
            pass
    return value


def _normalize_provider(provider: Optional[str]) -> Optional[str]:
    if not provider:
        return None
    p = provider.lower().strip()
    for variant in ("openai-codex",):
        if variant in p:
            return "openai"
    return p


def build_agent_input_attributes(
    session_id: str,
    model: str,
    user_message: str,
    service_name: str,
    platform: Optional[str] = None,
    sender_id: Optional[str] = None,
    is_first_turn: bool = False,
) -> Dict[str, Any]:
    attrs: Dict[str, Any] = {
        SA.OPENINFERENCE_SPAN_KIND: _SPAN_KIND_AGENT,
        SA.INPUT_VALUE: sanitize_string(user_message) if user_message else "",
        SA.INPUT_MIME_TYPE: "text/plain",
        SA.LLM_MODEL_NAME: model or "",
        SA.SESSION_ID: session_id,
        SA.AGENT_NAME: service_name,
    }
    if sender_id:
        attrs[SA.USER_ID] = sender_id
    metadata: Dict[str, Any] = {}
    if platform:
        metadata["platform"] = platform
    metadata["is_first_turn"] = is_first_turn
    if metadata:
        attrs[SA.METADATA] = metadata
    return attrs


def build_agent_output_attributes(
    assistant_response: Optional[str],
    model: Optional[str] = None,
    platform: Optional[str] = None,
    session_id: Optional[str] = None,
    tokens_prompt: Optional[int] = None,
    tokens_completion: Optional[int] = None,
    tokens_total: Optional[int] = None,
    completed: Optional[bool] = None,
    interrupted: Optional[bool] = None,
    duration_s: Optional[float] = None,
    api_call_count: int = 0,
    tool_call_count: int = 0,
    usage: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    attrs: Dict[str, Any] = {}
    if assistant_response is not None:
        attrs[SA.OUTPUT_VALUE] = sanitize_string(assistant_response)
        attrs[SA.OUTPUT_MIME_TYPE] = "text/plain"
    metadata: Dict[str, Any] = {}
    if platform:
        metadata["platform"] = platform
    if model:
        metadata["model"] = model
    if session_id:
        metadata["session_id"] = session_id
    if completed is not None:
        metadata["completed"] = completed
    if interrupted is not None:
        metadata["interrupted"] = interrupted
    if duration_s is not None:
        metadata["duration_s"] = round(duration_s, 2)
    if api_call_count:
        metadata["api_call_count"] = api_call_count
    if tool_call_count:
        metadata["tool_call_count"] = tool_call_count
    if usage:
        metadata["usage"] = usage
    if metadata:
        attrs[SA.METADATA] = metadata
    if tokens_prompt is not None:
        attrs[SA.LLM_TOKEN_COUNT_PROMPT] = tokens_prompt
    if tokens_completion is not None:
        attrs[SA.LLM_TOKEN_COUNT_COMPLETION] = tokens_completion
    if tokens_total is not None:
        attrs[SA.LLM_TOKEN_COUNT_TOTAL] = tokens_total
    return attrs


def build_llm_input_attributes(
    model: str = "",
    provider: str = "",
    user_message: Optional[str] = None,
    conversation_history: Optional[List[Dict[str, Any]]] = None,
    base_url: str = "",
    api_mode: str = "",
    api_call_count: int = 0,
    message_count: int = 0,
    tool_count: int = 0,
    approx_input_tokens: int = 0,
    max_tokens: int = 0,
    request_char_count: int = 0,
) -> Dict[str, Any]:
    attrs: Dict[str, Any] = {
        SA.OPENINFERENCE_SPAN_KIND: _SPAN_KIND_LLM,
        SA.LLM_MODEL_NAME: model or "",
    }

    normalized = _normalize_provider(provider)
    if normalized:
        attrs[SA.LLM_PROVIDER] = normalized

    if user_message is not None:
        messages = []
        if conversation_history:
            for msg in conversation_history:
                role = msg.get("role", "unknown")
                content = msg.get("content", "")
                if isinstance(content, list):
                    content = " ".join(
                        str(c.get("text", c)) if isinstance(c, dict) else str(c)
                        for c in content
                    )
                messages.append({"role": role, "content": sanitize_string(str(content))})
        messages.append({"role": "user", "content": sanitize_string(user_message or "")})

        input_data: Dict[str, Any] = {
            "prompt": sanitize_string(user_message or ""),
        }
        if conversation_history:
            input_data["history_messages"] = conversation_history
        attrs[SA.INPUT_VALUE] = input_data
        attrs[SA.INPUT_MIME_TYPE] = "application/json"
        attrs[SA.LLM_INPUT_MESSAGES] = messages

    invocation_params: Dict[str, Any] = {}
    if max_tokens:
        invocation_params["max_tokens"] = max_tokens
    if api_mode:
        invocation_params["api_mode"] = api_mode
    if model:
        invocation_params["model"] = model
    if provider:
        invocation_params["provider"] = provider
    if invocation_params:
        attrs[SA.LLM_INVOCATION_PARAMETERS] = invocation_params

    metadata: Dict[str, Any] = {"api_call_index": api_call_count}
    if message_count:
        metadata["message_count"] = message_count
    if tool_count:
        metadata["tool_count"] = tool_count
    if approx_input_tokens:
        metadata["approx_input_tokens"] = approx_input_tokens
    if request_char_count:
        metadata["request_char_count"] = request_char_count
    if base_url:
        metadata["base_url"] = base_url
    attrs[SA.METADATA] = metadata

    return attrs


def build_llm_output_attributes(
    assistant_response: Optional[str] = None,
    usage: Optional[Dict[str, Any]] = None,
    finish_reason: Optional[str] = None,
    api_duration: float = 0,
    response_model: str = "",
    assistant_content_chars: int = 0,
    assistant_tool_calls_count: int = 0,
    api_call_count: int = 0,
) -> Dict[str, Any]:
    attrs: Dict[str, Any] = {}

    output_messages = []
    if assistant_response:
        output_messages.append(
            {"role": "assistant", "content": sanitize_string(assistant_response)}
        )
        attrs[SA.OUTPUT_VALUE] = sanitize_string(assistant_response)
        attrs[SA.OUTPUT_MIME_TYPE] = "text/plain"

    if output_messages:
        attrs[SA.LLM_OUTPUT_MESSAGES] = output_messages

    if response_model:
        attrs[SA.LLM_MODEL_NAME] = response_model

    if usage:
        prompt_tokens = usage.get("prompt_tokens") or usage.get("input_tokens")
        completion_tokens = usage.get("completion_tokens") or usage.get("output_tokens")
        total_tokens = usage.get("total_tokens")

        if prompt_tokens is not None:
            attrs[SA.LLM_TOKEN_COUNT_PROMPT] = int(prompt_tokens)
        if completion_tokens is not None:
            attrs[SA.LLM_TOKEN_COUNT_COMPLETION] = int(completion_tokens)
        if total_tokens is not None:
            attrs[SA.LLM_TOKEN_COUNT_TOTAL] = int(total_tokens)

        cache_read = usage.get("cache_read_tokens")
        cache_write = usage.get("cache_write_tokens")
        reasoning = usage.get("reasoning_tokens")
        if cache_read is not None:
            attrs[SA.LLM_TOKEN_COUNT_PROMPT_DETAILS_CACHE_READ] = int(cache_read)
        if cache_write is not None:
            attrs[SA.LLM_TOKEN_COUNT_PROMPT_DETAILS_CACHE_WRITE] = int(cache_write)
        if reasoning is not None:
            attrs[SA.LLM_TOKEN_COUNT_COMPLETION_DETAILS_REASONING] = int(reasoning)

    metadata: Dict[str, Any] = {"api_call_index": api_call_count}
    if finish_reason:
        metadata["finish_reason"] = finish_reason
    if api_duration:
        metadata["latency_s"] = round(api_duration, 3)
    if response_model:
        metadata["response_model"] = response_model
    if assistant_content_chars:
        metadata["assistant_content_chars"] = assistant_content_chars
    if assistant_tool_calls_count:
        metadata["assistant_tool_calls_count"] = assistant_tool_calls_count
    attrs[SA.METADATA] = metadata

    return attrs


def build_tool_input_attributes(
    tool_name: str,
    args: Dict[str, Any],
) -> Dict[str, Any]:
    attrs: Dict[str, Any] = {
        SA.OPENINFERENCE_SPAN_KIND: _SPAN_KIND_TOOL,
        SA.TOOL_NAME: tool_name,
        SA.INPUT_VALUE: sanitize_value(args),
        SA.INPUT_MIME_TYPE: "application/json",
    }
    return attrs


def build_tool_output_attributes(
    result: Any,
    is_error: bool = False,
) -> Dict[str, Any]:
    attrs: Dict[str, Any] = {}
    if is_error:
        parsed = _try_parse_json(result)
        if isinstance(parsed, (dict, list)):
            attrs[SA.OUTPUT_VALUE] = parsed
        else:
            attrs[SA.OUTPUT_VALUE] = {"error": str(result)}
    else:
        parsed = _try_parse_json(result)
        if isinstance(parsed, (dict, list)):
            attrs[SA.OUTPUT_VALUE] = sanitize_value(parsed)
        else:
            attrs[SA.OUTPUT_VALUE] = sanitize_value(result)
    attrs[SA.OUTPUT_MIME_TYPE] = "application/json"
    return attrs
