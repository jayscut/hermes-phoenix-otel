from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

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
    started_at: float = 0.0
    last_activity_at: float = 0.0
    usage: Usage = field(default_factory=Usage)
    model: Optional[str] = None
    provider: Optional[str] = None
    output: Optional[str] = None
    user_message: Optional[str] = None
    conversation_history: Optional[List[Dict[str, Any]]] = None
    sender_id: Optional[str] = None
    platform: Optional[str] = None
    api_call_count: int = 0
    tool_call_count: int = 0
    lock: threading.Lock = field(default_factory=threading.Lock)
