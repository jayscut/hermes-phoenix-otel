from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from opentelemetry import context as otel_context
from opentelemetry import trace
from opentelemetry.trace import Span, SpanKind, Status, StatusCode

from .models import PhoenixConfig

logger = logging.getLogger("hermes-phoenix-otel")

_provider = None
_tracer: Optional[trace.Tracer] = None


def init_otel(config: PhoenixConfig) -> None:
    global _provider, _tracer

    try:
        from phoenix.otel import register as phoenix_register

        headers: Optional[Dict[str, str]] = None
        if config.api_key:
            headers = {"Authorization": f"Bearer {config.api_key}"}

        _provider = phoenix_register(
            endpoint=config.endpoint,
            project_name=config.project_name,
            batch=config.batch,
            set_global_tracer_provider=False,
            headers=headers,
            verbose=False,
        )
        _tracer = _provider.get_tracer("hermes-phoenix-otel", "1.0.0")
        logger.info(
            "Phoenix OTEL initialized: endpoint=%s project=%s",
            config.endpoint,
            config.project_name,
        )
    except Exception as exc:
        logger.warning("[phoenix-otel] Failed to initialize OTel: %s", exc)
        _provider = None
        _tracer = None


def get_tracer() -> Optional[trace.Tracer]:
    return _tracer


def start_root_span(
    name: str,
    attributes: Optional[Dict[str, Any]] = None,
) -> Optional[Span]:
    t = get_tracer()
    if t is None:
        return None
    try:
        span = t.start_span(name, attributes=attributes, kind=SpanKind.INTERNAL)
        return span
    except Exception as exc:
        logger.warning("[phoenix-otel] Failed to start root span: %s", exc)
        return None


def start_child_span(
    parent: Span,
    name: str,
    attributes: Optional[Dict[str, Any]] = None,
    kind: SpanKind = SpanKind.INTERNAL,
) -> Optional[Span]:
    t = get_tracer()
    if t is None:
        return None
    try:
        ctx = trace.set_span_in_context(parent, otel_context.get_current())
        span = t.start_span(name, attributes=attributes, kind=kind, context=ctx)
        return span
    except Exception as exc:
        logger.warning("[phoenix-otel] Failed to start child span: %s", exc)
        return None


def end_span(span: Optional[Span], status: Optional[Status] = None) -> None:
    if span is None:
        return
    try:
        if status is not None:
            span.set_status(status)
        span.end()
    except Exception as exc:
        logger.warning("[phoenix-otel] Failed to end span: %s", exc)


def set_span_attributes(span: Optional[Span], attributes: Dict[str, Any]) -> None:
    if span is None:
        return
    try:
        for key, value in attributes.items():
            if value is not None:
                span.set_attribute(key, value)
    except Exception as exc:
        logger.warning("[phoenix-otel] Failed to set span attributes: %s", exc)


def force_flush() -> None:
    if _provider is not None:
        try:
            _provider.force_flush()
        except Exception as exc:
            logger.warning("[phoenix-otel] Force flush failed: %s", exc)


def shutdown() -> None:
    global _provider, _tracer
    if _provider is not None:
        try:
            _provider.force_flush()
            _provider.shutdown()
        except Exception as exc:
            logger.warning("[phoenix-otel] Shutdown failed: %s", exc)
    _provider = None
    _tracer = None
