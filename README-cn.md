# Hermes Phoenix OTEL 插件

通过 OpenTelemetry 将 LLM traces 和 spans 导出到 [Phoenix](https://phoenix.arize.com/) (Arize)，遵循 [OpenInference](https://github.com/Arize-ai/openinference) 语义约定。

这是 [openclaw-phoenix-otel](https://github.com/Arize-ai/openclaw-phoenix-otel) 面向 [Hermes Agent](https://hermes-agent.nousresearch.com/) 插件系统的完整 Python 移植。

## 功能

- **三层 Span 层级**: 每次 turn 生成 AGENT → LLM + TOOL spans
- **OpenInference 语义约定**: Phoenix UI 原生渲染
- **Token 追踪**: prompt、completion、cache read/write、reasoning tokens
- **过期 Trace 清理**: 可配置的后台清理线程
- **载荷清洗**: 导出前移除内部标记和图片引用
- **Hermes 配置集成**: 使用 `config.yaml` 中的 `phoenix_otel` 命名空间

## 安装

```bash
# 克隆到 Hermes 插件目录
git clone <repo-url> ~/.hermes/plugins/phoenix-otel
```

Hermes 会在下次启动时自动发现插件。所需的 pip 依赖（`arize-phoenix-otel`）会通过 `plugin.yaml` 中的 `pip_dependencies` 自动安装。

## 配置

三级优先级: **config.yaml** > **环境变量** > **默认值**。

### 通过 config.yaml

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

通过 `hermes config set` 管理:

```bash
hermes config set phoenix_otel.endpoint https://my-phoenix.example.com
hermes config set phoenix_otel.api_key ${PHOENIX_API_KEY}
hermes config set phoenix_otel.project_name production-app
```

### 通过环境变量

| 变量 | 默认值 |
|---|---|
| `PHOENIX_COLLECTOR_ENDPOINT` | `http://localhost:6006/v1/traces` |
| `PHOENIX_API_KEY` | _(无)_ |
| `PHOENIX_PROJECT_NAME` | `hermes-agent` |

### 全部配置项

| 键 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `endpoint` | string | `http://localhost:6006/v1/traces` | Phoenix collector 端点 |
| `api_key` | string | _(无)_ | API 密钥 (Bearer token) |
| `project_name` | string | `hermes-agent` | Phoenix 项目名 |
| `service_name` | string | `hermes-agent` | OTel 服务名 |
| `batch` | bool | `true` | 使用 BatchSpanProcessor |
| `stale_timeout_ms` | int | `300000` | 过期 trace 超时时间 |
| `stale_sweep_interval_ms` | int | `60000` | 过期 trace 清理间隔 |
| `stale_trace_cleanup_enabled` | bool | `true` | 是否启用过期 trace 清理 |

## Span 层级

每次 agent turn 产生:

```
AGENT span (根)
├── input: 用户提示
├── output: 最终助手回复
├── llm.model_name, session.id, agent.name
│
├── LLM span
│   ├── input: JSON(prompt, history)
│   ├── output: 助手回复
│   ├── llm.input_messages / llm.output_messages
│   └── llm.token_count.prompt / completion / total
│
└── TOOL span(s)
    ├── tool.name
    ├── input: JSON(args)
    └── output: JSON(result)
```

## Hook 覆盖

| Hermes Hook | 动作 |
|---|---|
| `on_session_start` | Session 元数据 |
| `pre_llm_call` | 创建 AGENT + LLM spans |
| `pre_api_request` | Provider/model 元数据 |
| `post_api_request` | Token 计数, usage |
| `pre_tool_call` | 创建 TOOL span |
| `post_tool_call` | 结束 TOOL span 并记录结果 |
| `post_llm_call` | 结束 LLM span 并记录输出 |
| `on_session_end` | 结束 AGENT span, flush |
| `on_session_finalize` | Flush + shutdown |
| `on_session_reset` | 清理旧 traces |

## 快速开始

1. 启动本地 Phoenix 服务器:

```bash
pip install arize-phoenix
python -m phoenix.server.main serve
```

2. 安装插件:

```bash
git clone <repo-url> ~/.hermes/plugins/phoenix-otel
```

3. 启动 Hermes — traces 将出现在 `http://localhost:6006`。

## 架构

```
hermes-phoenix-otel/
├── plugin.yaml              # 清单 (hooks, pip_dependencies)
├── __init__.py              # register(ctx) + hook 回调
├── otel_bridge.py           # arize-phoenix-otel 初始化 + span CRUD
├── span_builder.py          # AGENT/LLM/TOOL 属性构建器
├── payload_sanitizer.py     # 内容清洗
├── config.py                # 配置解析
└── models.py                # PhoenixConfig, ActiveTrace 数据类
```

## 许可证

Apache-2.0
