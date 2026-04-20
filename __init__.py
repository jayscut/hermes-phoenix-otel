"""
Hermes Phoenix OTEL Plugin — export LLM traces to Phoenix (Arize) via OpenTelemetry.

Complete port of openclaw-phoenix-otel to the Hermes plugin system.
Uses arize-phoenix-otel for Phoenix-aware OTel initialization and
openinference-semantic-conventions for span attribute names.
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Any, Dict, Optional

from opentelemetry.trace import Span, Status, StatusCode

from .config import resolve_config
from .otel_bridge import (
    end_span,
    force_flush,
    init_otel,
    set_span_attributes,
    shutdown,
    start_child_span,
    start_root_span,
)
from .span_builder import (
    build_agent_input_attributes,
    build_agent_output_attributes,
    build_llm_input_attributes,
    build_llm_output_attributes,
    build_tool_input_attributes,
    build_tool_output_attributes,
)
from .models import ActiveTrace, PhoenixConfig

logger = logging.getLogger("hermes-phoenix-otel")

_active_traces: Dict[str, ActiveTrace] = {}
_traces_lock = threading.Lock()
_config: Optional[PhoenixConfig] = None
_sweep_thread: Optional[threading.Thread] = None
_sweep_stop = threading.Event()


def _get_trace(session_id: str) -> Optional[ActiveTrace]:
    with _traces_lock:
        return _active_traces.get(session_id)


def _put_trace(session_id: str, trace_state: ActiveTrace) -> None:
    with _traces_lock:
        _active_traces[session_id] = trace_state


def _remove_trace(session_id: str) -> None:
    with _traces_lock:
        _active_traces.pop(session_id, None)


def _touch_activity(trace_state: ActiveTrace) -> None:
    trace_state.last_activity_at = time.time()


def _stale_sweep_loop() -> None:
    if _config is None:
        return
    while not _sweep_stop.wait(timeout=_config.stale_sweep_interval_ms / 1000.0):
        try:
            _sweep_stale_traces()
        except Exception as exc:
            logger.warning("[phoenix-otel] Stale sweep error: %s", exc)


def _sweep_stale_traces() -> None:
    if _config is None:
        return
    now = time.time()
    timeout_secs = _config.stale_timeout_ms / 1000.0
    stale_ids = []

    with _traces_lock:
        for sid, tr in _active_traces.items():
            if (now - tr.last_activity_at) > timeout_secs:
                stale_ids.append(sid)

    for sid in stale_ids:
        tr = _get_trace(sid)
        if tr is None:
            continue
        logger.warning("[phoenix-otel] Cleaning up stale trace: %s", sid)
        try:
            with tr.lock:
                for span in list(tr.tool_spans.values()):
                    end_span(span, Status(StatusCode.ERROR, "Stale trace cleaned up"))
                tr.tool_spans.clear()
                for span in list(tr.subagent_spans.values()):
                    end_span(span, Status(StatusCode.ERROR, "Stale trace cleaned up"))
                tr.subagent_spans.clear()
                if tr.llm_span is not None:
                    end_span(
                        tr.llm_span, Status(StatusCode.ERROR, "Stale trace cleaned up")
                    )
                    tr.llm_span = None
                end_span(
                    tr.root_span, Status(StatusCode.ERROR, "Stale trace cleaned up")
                )
        except Exception as exc:
            logger.warning("[phoenix-otel] Error cleaning stale trace %s: %s", sid, exc)
        _remove_trace(sid)

    if stale_ids:
        force_flush()


def _on_session_start(session_id: str, model: str = "", platform: str = "", **kwargs) -> None:
    logger.debug("[phoenix-otel] Session started: %s model=%s platform=%s", session_id, model, platform)


def _on_pre_llm_call(
    session_id: str,
    user_message: str = "",
    conversation_history: Optional[list] = None,
    is_first_turn: bool = False,
    model: str = "",
    platform: str = "",
    sender_id: Optional[str] = None,
    **kwargs,
) -> None:
    if _config is None:
        return
    try:
        existing = _get_trace(session_id)
        if existing is not None:
            _finalize_trace(existing, session_id)

        agent_attrs = build_agent_input_attributes(
            session_id=session_id,
            model=model,
            user_message=user_message or "",
            service_name=_config.service_name,
            platform=platform,
            sender_id=sender_id,
        )
        root_span = start_root_span(f"Agent: {session_id}", agent_attrs)
        if root_span is None:
            return

        llm_attrs = build_llm_input_attributes(
            model=model,
            provider=None,
            user_message=user_message or "",
            conversation_history=conversation_history,
        )
        llm_span = start_child_span(root_span, "LLM", llm_attrs)

        trace_state = ActiveTrace(
            root_span=root_span,
            llm_span=llm_span,
            started_at=time.time(),
            last_activity_at=time.time(),
            model=model,
            user_message=user_message,
            sender_id=sender_id,
        )
        _put_trace(session_id, trace_state)
    except Exception as exc:
        logger.warning("[phoenix-otel] pre_llm_call error: %s", exc)


def _on_pre_api_request(
    task_id: str = "",
    session_id: str = "",
    platform: str = "",
    model: str = "",
    provider: str = "",
    base_url: str = "",
    api_mode: str = "",
    api_call_count: int = 0,
    message_count: int = 0,
    tool_count: int = 0,
    approx_input_tokens: int = 0,
    request_char_count: int = 0,
    max_tokens: int = 0,
    **kwargs,
) -> None:
    tr = _get_trace(session_id)
    if tr is None:
        return
    try:
        _touch_activity(tr)
        extra_attrs: Dict[str, Any] = {}
        if provider:
            from .span_builder import _normalize_provider

            normalized = _normalize_provider(provider)
            if normalized and tr.llm_span is not None:
                from openinference.semconv.trace import SpanAttributes as SA

                set_span_attributes(tr.llm_span, {SA.LLM_PROVIDER: normalized})
    except Exception as exc:
        logger.warning("[phoenix-otel] pre_api_request error: %s", exc)


def _on_post_api_request(
    task_id: str = "",
    session_id: str = "",
    platform: str = "",
    model: str = "",
    provider: str = "",
    base_url: str = "",
    api_mode: str = "",
    api_call_count: int = 0,
    api_duration: float = 0,
    finish_reason: str = "",
    message_count: int = 0,
    response_model: str = "",
    usage: Optional[Dict[str, Any]] = None,
    assistant_content_chars: int = 0,
    assistant_tool_calls_count: int = 0,
    **kwargs,
) -> None:
    tr = _get_trace(session_id)
    if tr is None:
        return
    try:
        _touch_activity(tr)
        if tr.llm_span is None:
            return

        llm_output_attrs = build_llm_output_attributes(
            usage=usage,
            finish_reason=finish_reason,
        )
        set_span_attributes(tr.llm_span, llm_output_attrs)

        if usage:
            prompt_tokens = usage.get("prompt_tokens") or usage.get("input_tokens")
            completion_tokens = usage.get("completion_tokens") or usage.get("output_tokens")
            total_tokens = usage.get("total_tokens")
            if prompt_tokens is not None:
                tr.usage.input = int(prompt_tokens)
            if completion_tokens is not None:
                tr.usage.output = int(completion_tokens)
            if total_tokens is not None:
                tr.usage.total = int(total_tokens)
    except Exception as exc:
        logger.warning("[phoenix-otel] post_api_request error: %s", exc)


def _on_pre_tool_call(
    tool_name: str = "",
    args: Optional[Dict[str, Any]] = None,
    task_id: str = "",
    session_id: str = "",
    tool_call_id: str = "",
    **kwargs,
) -> None:
    tr = _get_trace(session_id)
    if tr is None:
        return
    try:
        _touch_activity(tr)
        tool_attrs = build_tool_input_attributes(
            tool_name=tool_name,
            args=args or {},
        )
        span = start_child_span(tr.root_span, f"Tool: {tool_name}", tool_attrs)
        if span is not None:
            key = tool_call_id or f"{tool_name}:{time.time()}"
            with tr.lock:
                tr.tool_spans[key] = span
    except Exception as exc:
        logger.warning("[phoenix-otel] pre_tool_call error: %s", exc)


def _on_post_tool_call(
    tool_name: str = "",
    args: Optional[Dict[str, Any]] = None,
    result: Any = None,
    task_id: str = "",
    session_id: str = "",
    tool_call_id: str = "",
    **kwargs,
) -> None:
    tr = _get_trace(session_id)
    if tr is None:
        return
    try:
        _touch_activity(tr)
        with tr.lock:
            span = tr.tool_spans.pop(tool_call_id, None)
            if span is None:
                for key in list(tr.tool_spans.keys()):
                    if key.startswith(tool_name):
                        span = tr.tool_spans.pop(key)
                        break

        if span is None:
            return

        is_error = isinstance(result, str) and '"error"' in result.lower()
        output_attrs = build_tool_output_attributes(result, is_error=is_error)
        set_span_attributes(span, output_attrs)

        status = (
            Status(StatusCode.ERROR, str(result)[:200])
            if is_error
            else Status(StatusCode.OK)
        )
        end_span(span, status)
    except Exception as exc:
        logger.warning("[phoenix-otel] post_tool_call error: %s", exc)


def _on_post_llm_call(
    session_id: str = "",
    user_message: str = "",
    assistant_response: str = "",
    conversation_history: Optional[list] = None,
    model: str = "",
    platform: str = "",
    **kwargs,
) -> None:
    tr = _get_trace(session_id)
    if tr is None:
        return
    try:
        _touch_activity(tr)
        tr.output = assistant_response

        if tr.llm_span is not None:
            from openinference.semconv.trace import SpanAttributes as SA

            set_span_attributes(
                tr.llm_span,
                {
                    SA.OUTPUT_VALUE: assistant_response or "",
                    SA.OUTPUT_MIME_TYPE: "text/plain",
                },
            )
            output_msgs = [{"role": "assistant", "content": assistant_response or ""}]
            set_span_attributes(
                tr.llm_span,
                {SA.LLM_OUTPUT_MESSAGES: _safe_json_output(output_msgs)},
            )
            end_span(tr.llm_span, Status(StatusCode.OK))
            tr.llm_span = None
    except Exception as exc:
        logger.warning("[phoenix-otel] post_llm_call error: %s", exc)


def _on_session_end(
    session_id: str = "",
    completed: bool = False,
    interrupted: bool = False,
    model: str = "",
    platform: str = "",
    **kwargs,
) -> None:
    tr = _get_trace(session_id)
    if tr is None:
        return
    try:
        _finalize_trace(tr, session_id)
    except Exception as exc:
        logger.warning("[phoenix-otel] on_session_end error: %s", exc)


def _on_session_finalize(
    session_id: Optional[str] = None,
    platform: str = "",
    **kwargs,
) -> None:
    try:
        if session_id:
            tr = _get_trace(session_id)
            if tr is not None:
                _finalize_trace(tr, session_id)

        with _traces_lock:
            for sid in list(_active_traces.keys()):
                tr = _active_traces.pop(sid, None)
                if tr is not None:
                    _finalize_trace_nolock(tr)

        force_flush()
    except Exception as exc:
        logger.warning("[phoenix-otel] on_session_finalize error: %s", exc)


def _on_session_reset(
    session_id: str = "",
    platform: str = "",
    **kwargs,
) -> None:
    tr = _get_trace(session_id)
    if tr is not None:
        _finalize_trace(tr, session_id)


def _finalize_trace(tr: ActiveTrace, session_id: str) -> None:
    _finalize_trace_nolock(tr)
    _remove_trace(session_id)


def _finalize_trace_nolock(tr: ActiveTrace) -> None:
    try:
        with tr.lock:
            for span in list(tr.tool_spans.values()):
                end_span(span, Status(StatusCode.ERROR, "Trace finalized"))
            tr.tool_spans.clear()

            for span in list(tr.subagent_spans.values()):
                end_span(span, Status(StatusCode.ERROR, "Trace finalized"))
            tr.subagent_spans.clear()

            if tr.llm_span is not None:
                end_span(tr.llm_span, Status(StatusCode.OK))
                tr.llm_span = None

            output_attrs = build_agent_output_attributes(
                assistant_response=tr.output,
                model=tr.model,
                tokens_prompt=tr.usage.input,
                tokens_completion=tr.usage.output,
                tokens_total=tr.usage.total,
            )
            set_span_attributes(tr.root_span, output_attrs)
            end_span(tr.root_span, Status(StatusCode.OK))
    except Exception as exc:
        logger.warning("[phoenix-otel] finalize trace error: %s", exc)


def _safe_json_output(obj: Any) -> str:
    import json

    try:
        return json.dumps(obj, default=str, ensure_ascii=False)
    except Exception:
        return "[]"


def register(ctx) -> None:
    global _config

    try:
        _config = resolve_config()
    except Exception as exc:
        logger.warning("[phoenix-otel] Config resolution failed: %s", exc)
        return

    try:
        init_otel(_config)
    except Exception as exc:
        logger.warning("[phoenix-otel] OTel initialization failed: %s", exc)
        return

    if _config.stale_trace_cleanup_enabled:
        t = threading.Thread(target=_stale_sweep_loop, daemon=True, name="phoenix-otel-stale-sweep")
        t.start()

    ctx.register_hook("on_session_start", _on_session_start)
    ctx.register_hook("pre_llm_call", _on_pre_llm_call)
    ctx.register_hook("pre_api_request", _on_pre_api_request)
    ctx.register_hook("post_api_request", _on_post_api_request)
    ctx.register_hook("pre_tool_call", _on_pre_tool_call)
    ctx.register_hook("post_tool_call", _on_post_tool_call)
    ctx.register_hook("post_llm_call", _on_post_llm_call)
    ctx.register_hook("on_session_end", _on_session_end)
    ctx.register_hook("on_session_finalize", _on_session_finalize)
    ctx.register_hook("on_session_reset", _on_session_reset)

    logger.info(
        "[phoenix-otel] Plugin registered: endpoint=%s project=%s",
        _config.endpoint,
        _config.project_name,
    )
