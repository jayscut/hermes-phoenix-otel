# Hermes Phoenix OTEL Plugin

Export LLM traces and spans to [Phoenix](https://phoenix.arize.com/) (Arize) via OpenTelemetry, using [OpenInference](https://github.com/Arize-ai/openinference) semantic conventions.

A complete Python port of [openclaw-phoenix-otel](https://github.com/Arize-ai/openclaw-phoenix-otel) for the [Hermes Agent](https://hermes-agent.nousresearch.com/) plugin system.

## Features

- **Three-level span hierarchy**: AGENT → LLM + TOOL spans per turn
- **OpenInference semantic conventions**: native Phoenix UI rendering
- **Token tracking**: prompt, completion, cache read/write, reasoning tokens
- **Stale trace cleanup**: configurable background sweep for abandoned traces
- **Payload sanitization**: strips internal markers and image references before export
- **Hermes config integration**: `phoenix_otel` namespace in `config.yaml`

## Installation

```bash
# 1. Install the Python dependency
pip install arize-phoenix-otel

# 2. Clone into the Hermes plugins directory
git clone <repo-url> ~/.hermes/plugins/phoenix-otel
```

Hermes auto-discovers plugins on next startup. The plugin will log a clear warning with install instructions if the dependency is missing.

## Configuration

Three-tier precedence: **config.yaml** > **environment variables** > **defaults**.

### Via config.yaml

```yaml
phoenix_otel:
  endpoint: https://app.phoenix.arize.com
  api_key: ${PHOENIX_API_KEY}
  project_name: hermes-agent
  service_name: hermes-agent
  batch: true
  stale_timeout_ms: 300000
  stale_sweep_interval_ms: 60000
```

Manage with `hermes config set`:

```bash
hermes config set phoenix_otel.endpoint https://my-phoenix.example.com
hermes config set phoenix_otel.api_key ${PHOENIX_API_KEY}
hermes config set phoenix_otel.project_name production-app
```

### Via environment variables

| Variable | Default |
|---|---|
| `PHOENIX_COLLECTOR_ENDPOINT` | `http://localhost:6006/v1/traces` |
| `PHOENIX_API_KEY` | _(none)_ |
| `PHOENIX_PROJECT_NAME` | `hermes-agent` |

### All options

| Key | Type | Default | Description |
|---|---|---|---|
| `endpoint` | string | `http://localhost:6006/v1/traces` | Phoenix collector endpoint |
| `api_key` | string | _(none)_ | API key (Bearer token) |
| `project_name` | string | `hermes-agent` | Phoenix project name |
| `service_name` | string | `hermes-agent` | OTel service name |
| `batch` | bool | `true` | Use BatchSpanProcessor |
| `stale_timeout_ms` | int | `300000` | Inactivity timeout for stale traces |
| `stale_sweep_interval_ms` | int | `60000` | How often to sweep for stale traces |
| `stale_trace_cleanup_enabled` | bool | `true` | Enable stale trace cleanup |

## Span Hierarchy

Each agent turn produces:

```
AGENT span (root)
├── input: user prompt
├── output: final assistant response
├── llm.model_name, session.id, agent.name
│
├── LLM span
│   ├── input: JSON(prompt, history)
│   ├── output: assistant response
│   ├── llm.input_messages / llm.output_messages
│   └── llm.token_count.prompt / completion / total
│
└── TOOL span(s)
    ├── tool.name
    ├── input: JSON(args)
    └── output: JSON(result)
```

## Hook Coverage

| Hermes Hook | Action |
|---|---|
| `on_session_start` | Session metadata |
| `pre_llm_call` | Create AGENT + LLM spans |
| `pre_api_request` | Provider/model metadata |
| `post_api_request` | Token counts, usage |
| `pre_tool_call` | Create TOOL span |
| `post_tool_call` | End TOOL span with result |
| `post_llm_call` | End LLM span with output |
| `on_session_end` | End AGENT span, flush |
| `on_session_finalize` | Flush + shutdown |
| `on_session_reset` | Cleanup old traces |

## Quick Start

1. Start a local Phoenix server:

```bash
pip install arize-phoenix
python -m phoenix.server.main serve
```

2. Install the plugin:

```bash
git clone <repo-url> ~/.hermes/plugins/phoenix-otel
```

3. Start Hermes — traces appear at `http://localhost:6006`.

## Architecture

```
hermes-phoenix-otel/
├── plugin.yaml              # Manifest (hooks, pip_dependencies)
├── __init__.py              # register(ctx) + hook callbacks
├── otel_bridge.py           # arize-phoenix-otel init + span CRUD
├── span_builder.py          # AGENT/LLM/TOOL attribute builders
├── payload_sanitizer.py     # Content sanitization
├── config.py                # Config resolution
└── models.py                # PhoenixConfig, ActiveTrace dataclasses
```

## License

Apache-2.0
