from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from opentelemetry.trace import Span


@dataclass
class PhoenixConfig:
    endpoint: str = "http://localhost:6006/v1/traces"
    api_key: Optional[str] = None
    project_name: str = "hermes-agent"
    service_name: str = "hermes-agent"
    batch: bool = True
    stale_timeout_ms: int = 300_000
    stale_sweep_interval_ms: int = 60_000
    stale_trace_cleanup_enabled: bool = True


@dataclass
class CostMeta:
    cost_usd: Optional[float] = None
    context_limit: Optional[int] = None
    context_used: Optional[int] = None
    model: Optional[str] = None
    provider: Optional[str] = None
    duration_ms: Optional[float] = None
    usage_input: Optional[int] = None
    usage_output: Optional[int] = None
    usage_cache_read: Optional[int] = None
    usage_cache_write: Optional[int] = None
    usage_total: Optional[int] = None


@dataclass
class Usage:
    input: Optional[int] = None
    output: Optional[int] = None
    cache_read: Optional[int] = None
    cache_write: Optional[int] = None
    reasoning: Optional[int] = None
    total: Optional[int] = None


@dataclass
class ActiveTrace:
    root_span: Span
    llm_span: Optional[Span] = None
    tool_spans: Dict[str, Span] = field(default_factory=dict)
    subagent_spans: Dict[str, Span] = field(default_factory=dict)
    started_at: float = 0.0
    last_activity_at: float = 0.0
    cost_meta: CostMeta = field(default_factory=CostMeta)
    usage: Usage = field(default_factory=Usage)
    model: Optional[str] = None
    provider: Optional[str] = None
    output: Optional[str] = None
    user_message: Optional[str] = None
    sender_id: Optional[str] = None
    platform: Optional[str] = None
    api_call_count: int = 0
    tool_call_count: int = 0
    lock: threading.Lock = field(default_factory=threading.Lock)
