# claw-turbo

**Zero-latency, zero-ML skill routing middleware for OpenClaw**

claw-turbo sits between your OpenClaw gateway and the LLM (Ollama), intercepting user messages that match predefined regex patterns and executing the corresponding skill scripts directly — no LLM inference needed.

## Why?

| Approach | Latency | Accuracy | Dependencies |
|----------|---------|----------|--------------|
| **claw-turbo** (regex) | **< 1ms** | **100%** | PyYAML only |
| LLM routing (Gemma 26B) | 2-10s | ~80% | Ollama + 16GB VRAM |
| Semantic routing (embeddings) | 50-200ms | ~95% | embedding model |

Local LLMs like Gemma 4 26B are powerful but unreliable for simple, repetitive skill calls:
- They don't always follow SKILL.md instructions strictly
- They "improvise" by adding wrong parameters
- Context window limitations cause instruction loss

For commands that can be matched with regex (e.g., "打印 GCXU5439046 资料"), letting an LLM decide is wasteful. claw-turbo handles these instantly and perfectly, while passing complex queries through to the LLM.

## Installation

```bash
cd tools/claw-turbo
pip install -e .
```

## Quick Start

### Test a message
```bash
claw-turbo test "打印 GCXU5439046 资料"
# MATCHED: print-container-all
#   Captures:    {'container': 'GCXU5439046'}
#   Match time:  12.3us
```

### List all routes
```bash
claw-turbo routes
```

### Start proxy server
```bash
claw-turbo serve --port 11435
```

Then update OpenClaw's Ollama `baseUrl` from `http://127.0.0.1:11434` to `http://127.0.0.1:11435`.

## Integration

### Option A: HTTP Proxy (Recommended)

claw-turbo runs as a transparent HTTP proxy between OpenClaw and Ollama:

```
User Message → OpenClaw → claw-turbo (port 11435) → Ollama (port 11434)
                              ↓ (if matched)
                         Execute skill script
                              ↓
                         Return response directly
```

```bash
# Start the proxy
claw-turbo serve

# Update ~/.openclaw/openclaw.json:
# Change baseUrl from http://127.0.0.1:11434 to http://127.0.0.1:11435
```

### Option B: OpenClaw Hook

Run as a pre-message hook that reads from stdin:

```bash
echo '{"message": "打印 GCXU5439046 资料"}' | claw-turbo hook
```

See `claw-turbo install` for detailed integration instructions.

## Route Configuration

Routes are defined in `routes.yaml`:

```yaml
routes:
  - name: print-container-all
    description: "打印柜号全部资料"
    patterns:
      - '打印\s*(?P<container>[A-Z]{4}\d{7})\s*(的)?\s*(资料|全部|所有)'
      - 'print\s+(?P<container>[A-Z]{4}\d{7})'
    command: 'bash /path/to/run.sh "{{raw_message}}"'
    response_template: "已执行打印 {{container}} 全部资料"
```

### Fields

| Field | Description |
|-------|-------------|
| `name` | Unique route identifier |
| `description` | Human-readable description |
| `patterns` | List of regex patterns with named capture groups |
| `command` | Bash command template. `{{raw_message}}` = original message, `{{group_name}}` = captured groups |
| `response_template` | Response sent back. Same template variables as `command` |

### Adding Routes from SKILL.md

```bash
claw-turbo add-skill /path/to/skill/directory
```

This reads the SKILL.md and generates a route template you can add to `routes.yaml`.

### Hot Reload

claw-turbo watches `routes.yaml` for changes and automatically reloads when the file is modified. No restart needed.

## CLI Reference

```
claw-turbo serve                     # Start HTTP proxy (default port 11435)
claw-turbo serve --port 8080         # Custom port
claw-turbo test "打印 GCXU5439046"    # Test message matching
claw-turbo routes                    # List all configured routes
claw-turbo add-skill <path>          # Generate route from SKILL.md
claw-turbo hook                      # Run as stdin hook (for OpenClaw integration)
claw-turbo install                   # Show installation instructions
```

## Running Tests

```bash
pip install pytest
pytest tests/ -v
```

## Architecture

```
claw_turbo/
├── cli.py        # CLI entry point (argparse)
├── config.py     # YAML loading + file watcher for hot reload
├── router.py     # Core regex matching engine
├── executor.py   # Subprocess-based bash command execution
├── proxy.py      # HTTP proxy server (stdlib http.server)
└── hook.py       # OpenClaw hook integration (stdin/stdout)
```

## License

MIT
