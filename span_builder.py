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


def _safe_json(obj: Any, max_len: int = 64000) -> str:
    try:
        s = json.dumps(obj, default=str, ensure_ascii=False)
        if len(s) > max_len:
            s = s[:max_len] + "...[truncated]"
        return s
    except Exception:
        return str(obj)[:max_len]


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
    return attrs


def build_agent_output_attributes(
    assistant_response: Optional[str],
    model: Optional[str] = None,
    platform: Optional[str] = None,
    session_id: Optional[str] = None,
    tokens_prompt: Optional[int] = None,
    tokens_completion: Optional[int] = None,
    tokens_total: Optional[int] = None,
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
    if metadata:
        attrs[SA.METADATA] = json.dumps(metadata)
    if tokens_prompt is not None:
        attrs[SA.LLM_TOKEN_COUNT_PROMPT] = tokens_prompt
    if tokens_completion is not None:
        attrs[SA.LLM_TOKEN_COUNT_COMPLETION] = tokens_completion
    if tokens_total is not None:
        attrs[SA.LLM_TOKEN_COUNT_TOTAL] = tokens_total
    return attrs


def build_llm_input_attributes(
    model: str,
    provider: Optional[str],
    user_message: str,
    conversation_history: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
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

    input_data = {
        "prompt": sanitize_string(user_message or ""),
        "history_messages": len(conversation_history) if conversation_history else 0,
    }

    attrs: Dict[str, Any] = {
        SA.OPENINFERENCE_SPAN_KIND: _SPAN_KIND_LLM,
        SA.INPUT_VALUE: _safe_json(input_data),
        SA.INPUT_MIME_TYPE: "application/json",
        SA.LLM_MODEL_NAME: model or "",
        SA.LLM_INPUT_MESSAGES: _safe_json(messages),
    }
    normalized = _normalize_provider(provider)
    if normalized:
        attrs[SA.LLM_PROVIDER] = normalized
    return attrs


def build_llm_output_attributes(
    assistant_response: Optional[str] = None,
    usage: Optional[Dict[str, Any]] = None,
    finish_reason: Optional[str] = None,
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
        attrs[SA.LLM_OUTPUT_MESSAGES] = _safe_json(output_messages)

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

        details = usage.get("prompt_tokens_details", {})
        if isinstance(details, dict):
            cache_read = details.get("cache_read_tokens") or details.get(
                "cached_tokens"
            )
            cache_write = details.get("cache_write_tokens") or details.get(
                "cache_creation_tokens"
            )
            if cache_read is not None:
                attrs[SA.LLM_TOKEN_COUNT_PROMPT_DETAILS_CACHE_READ] = int(cache_read)
            if cache_write is not None:
                attrs[SA.LLM_TOKEN_COUNT_PROMPT_DETAILS_CACHE_WRITE] = int(cache_write)

        completion_details = usage.get("completion_tokens_details", {})
        if isinstance(completion_details, dict):
            reasoning = completion_details.get("reasoning_tokens")
            if reasoning is not None:
                attrs[SA.LLM_TOKEN_COUNT_COMPLETION_DETAILS_REASONING] = int(reasoning)

    return attrs


def build_tool_input_attributes(
    tool_name: str,
    args: Dict[str, Any],
) -> Dict[str, Any]:
    attrs: Dict[str, Any] = {
        SA.OPENINFERENCE_SPAN_KIND: _SPAN_KIND_TOOL,
        SA.TOOL_NAME: tool_name,
        SA.INPUT_VALUE: _safe_json(sanitize_value(args)),
        SA.INPUT_MIME_TYPE: "application/json",
    }
    return attrs


def build_tool_output_attributes(
    result: Any,
    is_error: bool = False,
) -> Dict[str, Any]:
    attrs: Dict[str, Any] = {}
    if is_error:
        attrs[SA.OUTPUT_VALUE] = _safe_json({"error": str(result)})
    else:
        attrs[SA.OUTPUT_VALUE] = _safe_json(sanitize_value(result))
    attrs[SA.OUTPUT_MIME_TYPE] = "application/json"
    return attrs
