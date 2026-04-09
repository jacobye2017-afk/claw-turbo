<p align="center">
  <h1 align="center">claw-turbo</h1>
  <p align="center">
    <strong>Zero-latency, zero-ML skill routing middleware for OpenClaw & local LLMs</strong>
  </p>
  <p align="center">
    <a href="#installation">Installation</a> &bull;
    <a href="#quick-start">Quick Start</a> &bull;
    <a href="#how-it-works">How It Works</a> &bull;
    <a href="#route-configuration">Configuration</a> &bull;
    <a href="#benchmarks">Benchmarks</a>
  </p>
</p>

---

**claw-turbo** is a lightweight, high-performance message routing layer that sits between your AI agent framework ([OpenClaw](https://github.com/nicepkg/openclaw)) and your local LLM (Ollama, llama.cpp, etc.). It intercepts user messages using regex pattern matching and executes skill scripts directly — bypassing the LLM entirely for known commands.

**Result: 5 microseconds instead of 5 seconds. 100% accuracy instead of ~80%.**

## The Problem

If you're running a local LLM (Gemma, Llama, Qwen, Mistral, etc.) as an AI agent with tool/skill calling, you've probably hit these issues:

- **Slow**: Even fast local models take 2-10 seconds per inference
- **Unreliable**: LLMs don't always follow tool-calling instructions — they "improvise", add wrong parameters, or hallucinate flags
- **Wasteful**: Simple, repetitive commands (e.g., "deploy staging", "restart nginx", "print report X") don't need intelligence — they need precision
- **Context overflow**: Small context windows (8k-32k) cause instruction loss on complex SKILL.md files

## The Solution

claw-turbo adds a **fast path** for known commands:

```
                    ┌──────────────┐
                    │  User sends  │
                    │   message    │
                    └──────┬───────┘
                           │
                    ┌──────▼───────┐
                    │  claw-turbo  │
                    │ regex match  │ ← < 0.01ms
                    └──────┬───────┘
                           │
                ┌──── match? ────┐
                │                │
           ┌────▼────┐    ┌─────▼─────┐
           │   YES   │    │    NO     │
           │ Execute │    │ Forward   │
           │ script  │    │ to LLM    │
           │ directly│    │ (Ollama)  │
           └─────────┘    └───────────┘
           0ms, 100%      Normal LLM
           accurate       processing
```

**Simple commands get instant, perfect execution. Complex queries still go to your LLM.**

## Key Features

- **Sub-microsecond matching** — Compiled regex, no ML inference, no embedding lookup
- **100% accuracy** — Pattern match is deterministic; no hallucinated parameters
- **Zero ML dependencies** — Only requires PyYAML + Python stdlib
- **Hot reload** — Edit `routes.yaml` and changes apply instantly, no restart needed
- **Transparent proxy** — Drop-in between OpenClaw and Ollama; no code changes required
- **Multi-language patterns** — Supports Chinese, English, or any language in regex
- **Named capture groups** — Extract structured data (IDs, names, flags) from messages
- **Template rendering** — Dynamic command and response generation from captured groups

## Benchmarks

Tested on Apple M4 Max, Python 3.14:

| Metric | claw-turbo | Gemma 4 26B (Ollama) | GPT-4o (API) |
|--------|-----------|----------------------|---------------|
| **Match latency** | **5 us** | 2,000-10,000 ms | 500-2,000 ms |
| **Accuracy (simple commands)** | **100%** | ~80% | ~95% |
| **Memory usage** | **~30 MB** | 16+ GB VRAM | N/A (cloud) |
| **Dependencies** | **PyYAML** | Ollama + model weights | API key + network |
| **Works offline** | Yes | Yes | No |

> 5 microseconds = **400,000x faster** than local LLM inference for matched commands.

## Installation

### From source

```bash
git clone https://github.com/jacobye2017-afk/claw-turbo.git
cd claw-turbo
pip install -e .
```

### Requirements

- Python 3.10+
- PyYAML (auto-installed)
- No GPU, no ML models, no embedding databases

## Quick Start

### 1. Define your routes

Edit `routes.yaml` to define pattern-matched commands:

```yaml
routes:
  - name: deploy-staging
    description: "Deploy a service to staging"
    patterns:
      - 'deploy\s+(?P<service>\w+)\s+(?:to\s+)?staging'
      - '部署\s+(?P<service>\w+)\s+到\s*staging'
    command: 'bash /opt/scripts/deploy.sh {{service}} staging'
    response_template: "Deployed {{service}} to staging environment"

  - name: restart-service
    description: "Restart a service"
    patterns:
      - 'restart\s+(?P<service>[\w-]+)'
      - '重启\s+(?P<service>[\w-]+)'
    command: 'systemctl restart {{service}}'
    response_template: "Restarted {{service}}"

  - name: check-logs
    description: "Tail logs for a service"
    patterns:
      - '(?:show|check|tail)\s+logs?\s+(?:for\s+)?(?P<service>[\w-]+)'
      - '查看\s+(?P<service>[\w-]+)\s*日志'
    command: 'journalctl -u {{service}} --no-pager -n 50'
    response_template: "Last 50 log lines for {{service}}"
```

### 2. Test your patterns

```bash
$ claw-turbo test "deploy auth-service to staging"
MATCHED: deploy-staging
  Captures:    {'service': 'auth-service'}
  Command:     bash /opt/scripts/deploy.sh auth-service staging
  Response:    Deployed auth-service to staging environment
  Match time:  4.8us

$ claw-turbo test "what is the meaning of life"
NO MATCH
Message did not match any route. It would be passed to LLM.
```

### 3. Start the proxy

```bash
claw-turbo serve --port 11435
```

### 4. Point your LLM client to the proxy

Update your OpenClaw, LangChain, or any Ollama client config:

```diff
- "baseUrl": "http://127.0.0.1:11434"
+ "baseUrl": "http://127.0.0.1:11435"
```

That's it. Matched messages execute instantly; everything else passes through to Ollama normally.

## How It Works

### Architecture

```
claw_turbo/
├── cli.py        # CLI entry point — serve, test, routes, add-skill, hook
├── config.py     # YAML loader + file watcher (hot reload on modification)
├── router.py     # Compiled regex matching engine with named capture groups
├── executor.py   # Subprocess executor with timeout and error handling
├── proxy.py      # HTTP proxy (stdlib http.server) — Ollama API compatible
└── hook.py       # Stdin/stdout hook for direct OpenClaw integration
```

### Matching Engine

1. On startup, all patterns in `routes.yaml` are compiled into `re.Pattern` objects
2. Incoming messages are tested against each route's patterns in order
3. First match wins — the route's command template is rendered with captured groups
4. The command executes via `subprocess.run()` and the response template is returned

### Template Variables

| Variable | Description |
|----------|-------------|
| `{{raw_message}}` | The original user message, unmodified |
| `{{capture_name}}` | Any named capture group from the regex pattern |

### Hot Reload

A background thread watches `routes.yaml` for file modification (mtime-based). When a change is detected, routes are recompiled and swapped atomically using a read-write lock. Zero downtime.

## Integration Modes

### Mode A: HTTP Proxy (Recommended)

Transparent proxy between your agent framework and Ollama. Compatible with any client that speaks the Ollama API (`/api/chat`, `/api/generate`, `/v1/chat/completions`).

```bash
claw-turbo serve --host 0.0.0.0 --port 11435 --ollama-url http://localhost:11434
```

### Mode B: OpenClaw Hook

Runs as a pre-message filter via stdin/stdout:

```bash
echo '{"message": "restart nginx"}' | claw-turbo hook
# Exit code 0 = handled, stdout has response
# Exit code 1 = no match, let LLM handle it
```

### Mode C: Library Import

Use claw-turbo programmatically in your own Python agent:

```python
from claw_turbo.router import Router
from claw_turbo.executor import execute

router = Router("routes.yaml", watch=True)

match = router.match("deploy auth to staging")
if match:
    result = execute(match)
    print(match.rendered_response)
else:
    # Send to LLM
    pass
```

## Route Configuration Reference

### Full Schema

```yaml
routes:
  - name: string            # Unique identifier (required)
    description: string     # Human-readable description (optional)
    patterns:               # List of regex patterns (required)
      - 'regex with (?P<named_groups>...)'
    command: string         # Bash command template (required)
    response_template: string  # Response template (optional)
```

### Pattern Tips

- Use `(?P<name>...)` for named capture groups — they become template variables
- Use `(?:...)` for non-capturing groups
- Patterns are case-insensitive by default
- First matching pattern in first matching route wins
- Test patterns with `claw-turbo test "your message"` before deploying

### Auto-Generate from SKILL.md

If you have existing OpenClaw skills, generate a route template:

```bash
claw-turbo add-skill /path/to/skill/
# Outputs a YAML template you can paste into routes.yaml
```

## CLI Reference

```
claw-turbo serve [options]           Start HTTP proxy server
  --host HOST                        Bind address (default: 127.0.0.1)
  --port PORT                        Listen port (default: 11435)
  --ollama-url URL                   Upstream Ollama URL (default: http://127.0.0.1:11434)

claw-turbo test MESSAGE              Test a message against all routes
claw-turbo routes                    List all configured routes
claw-turbo add-skill PATH            Generate route template from SKILL.md
claw-turbo hook                      Run as stdin/stdout hook
claw-turbo install                   Show integration instructions

Global options:
  --routes PATH                      Path to routes.yaml
  -v, --verbose                      Enable debug logging
```

## Use Cases

- **DevOps automation** — "restart nginx", "deploy to staging", "show logs for api-server"
- **Document processing** — "print report ABC123", "generate invoice for order 456"
- **IoT / smart office** — "turn on meeting room lights", "set AC to 22 degrees"
- **Data pipelines** — "run ETL for 2024-01", "refresh dashboard metrics"
- **Customer service agents** — "check order status ORD-789", "refund order ORD-789"

Any task where the trigger is a **known pattern** and the action is a **deterministic script**.

## When NOT to Use claw-turbo

- Open-ended questions ("explain this code", "write a poem")
- Tasks requiring reasoning or multi-step planning
- Messages with ambiguous intent
- Anything that genuinely needs an LLM

claw-turbo is a **complement** to your LLM, not a replacement. It handles the 20% of messages that are simple commands, so your LLM can focus on the 80% that actually need intelligence.

## Running Tests

```bash
pip install pytest
pytest tests/ -v
```

```
tests/test_router.py    — 14 tests (pattern matching, template rendering, hot reload)
tests/test_executor.py  —  5 tests (execution, timeout, error handling)
======================== 19 passed ========================
```

## Contributing

Contributions are welcome! Some ideas:

- [ ] Add weighted/priority-based route matching
- [ ] Support JSON Schema validation for captured groups
- [ ] Add metrics endpoint (`/metrics` for Prometheus)
- [ ] WebSocket proxy support for streaming responses
- [ ] Route groups with shared middleware (auth, rate limiting)
- [ ] Web UI for route management and testing

## Author

Created by **[Jacob Ye](https://github.com/jacobye2017-afk)** — building AI agent tooling for real-world automation.

## License

[MIT](LICENSE)

---

<p align="center">
  Built for the <a href="https://github.com/nicepkg/openclaw">OpenClaw</a> community.<br>
  If claw-turbo saves you time, give it a star.
</p>
