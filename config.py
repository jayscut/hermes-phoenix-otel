from __future__ import annotations

import logging
import os
from typing import Optional

from .models import PhoenixConfig

logger = logging.getLogger("hermes-phoenix-otel")

DEFAULT_ENDPOINT = "http://localhost:6006/v1/traces"
DEFAULT_PROJECT_NAME = "hermes-agent"
DEFAULT_SERVICE_NAME = "hermes-agent"


def resolve_config() -> PhoenixConfig:
    cfg = _load_phoenix_config_section()

    endpoint = (
        _str(cfg.get("endpoint"))
        or os.getenv("PHOENIX_COLLECTOR_ENDPOINT")
        or DEFAULT_ENDPOINT
    )
    if not endpoint.rstrip("/").endswith("/v1/traces"):
        endpoint = endpoint.rstrip("/") + "/v1/traces"

    api_key = _str(cfg.get("api_key")) or os.getenv("PHOENIX_API_KEY")
    project_name = (
        _str(cfg.get("project_name"))
        or os.getenv("PHOENIX_PROJECT_NAME")
        or DEFAULT_PROJECT_NAME
    )
    service_name = _str(cfg.get("service_name")) or DEFAULT_SERVICE_NAME
    batch = cfg.get("batch", True) if isinstance(cfg.get("batch", True), bool) else True
    stale_timeout_ms = _int(cfg.get("stale_timeout_ms"), 300_000)
    stale_sweep_interval_ms = _int(cfg.get("stale_sweep_interval_ms"), 60_000)
    stale_cleanup = cfg.get("stale_trace_cleanup_enabled", True)
    if not isinstance(stale_cleanup, bool):
        stale_cleanup = True

    conf = PhoenixConfig(
        endpoint=endpoint,
        api_key=api_key,
        project_name=project_name,
        service_name=service_name,
        batch=batch,
        stale_timeout_ms=stale_timeout_ms,
        stale_sweep_interval_ms=stale_sweep_interval_ms,
        stale_trace_cleanup_enabled=stale_cleanup,
    )
    logger.debug(
        "Phoenix OTEL config resolved: endpoint=%s project=%s service=%s",
        conf.endpoint,
        conf.project_name,
        conf.service_name,
    )
    return conf


def _load_phoenix_config_section() -> dict:
    try:
        from hermes_cli.config import load_config

        config = load_config()
        section = config.get("phoenix_otel", {})
        if isinstance(section, dict):
            return section
    except Exception:
        pass
    return {}


def _str(val: object) -> Optional[str]:
    if isinstance(val, str):
        v = val.strip()
        return v if v else None
    return None


def _int(val: object, default: int) -> int:
    if isinstance(val, (int, float)) and not isinstance(val, bool):
        v = int(val)
        return v if v > 0 else default
    return default
