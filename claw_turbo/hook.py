"""OpenClaw hook integration: pre-message hook that intercepts matched messages."""

import json
import logging
import sys
from pathlib import Path

from .config import DEFAULT_ROUTES_PATH
from .router import Router
from .executor import execute

logger = logging.getLogger("claw-turbo")

OPENCLAW_CONFIG = Path.home() / ".openclaw" / "openclaw.json"


def run_hook(routes_path: Path | str | None = None):
    """
    Called as a pre-message hook by OpenClaw.

    Reads the user message from stdin (JSON format from OpenClaw hook system),
    checks for a route match, and either:
    - Executes the skill and prints the response (exit 0 to stop LLM processing)
    - Exits with code 1 to let OpenClaw continue to LLM
    """
    path = Path(routes_path) if routes_path else DEFAULT_ROUTES_PATH
    router = Router(path)

    # Read message from stdin (OpenClaw passes hook input as JSON)
    try:
        input_data = json.loads(sys.stdin.read())
    except (json.JSONDecodeError, EOFError):
        # If stdin is not JSON, try reading as plain text
        sys.exit(1)

    # Extract user message
    message = None
    if isinstance(input_data, dict):
        message = input_data.get("message", input_data.get("content", input_data.get("text")))
    elif isinstance(input_data, str):
        message = input_data

    if not message:
        sys.exit(1)  # No message, pass through to LLM

    match = router.match(message)
    if not match:
        sys.exit(1)  # No match, pass through to LLM

    # Execute the matched skill
    logger.info("Hook intercepted: %s -> %s", message[:60], match.route.name)
    exec_result = execute(match)

    # Output the response for OpenClaw
    response = match.rendered_response
    if not exec_result.success:
        response = f"命令执行失败: {exec_result.stderr[:200]}"

    output = {
        "response": response,
        "matched_route": match.route.name,
        "intercepted": True,
    }
    print(json.dumps(output, ensure_ascii=False))
    sys.exit(0)  # Exit 0 = message handled, don't send to LLM


def install_hook(openclaw_config: Path | None = None):
    """Show instructions for installing claw-turbo as an OpenClaw hook."""
    config_path = openclaw_config or OPENCLAW_CONFIG

    print("=== claw-turbo OpenClaw Hook Installation ===\n")

    if config_path.exists():
        with open(config_path, "r") as f:
            config = json.load(f)
        print(f"Found OpenClaw config at: {config_path}")
    else:
        print(f"OpenClaw config not found at: {config_path}")

    print("""
To integrate claw-turbo as a pre-message hook, add the following to your
OpenClaw configuration or startup script:

  Option 1: Environment variable
  ──────────────────────────────
  Export in your shell profile:

    export OPENCLAW_PRE_MESSAGE_HOOK="claw-turbo hook"

  Option 2: Wrapper script
  ────────────────────────
  Create a wrapper that pipes messages through claw-turbo first:

    #!/bin/bash
    # /usr/local/bin/openclaw-with-turbo
    echo "$1" | claw-turbo hook
    if [ $? -eq 0 ]; then
        exit 0  # claw-turbo handled it
    fi
    # Fall through to normal OpenClaw processing

  Option 3: Proxy mode (recommended for production)
  ─────────────────────────────────────────────────
  Run claw-turbo as an HTTP proxy:

    claw-turbo serve --port 11435

  Then update OpenClaw's Ollama baseUrl to http://127.0.0.1:11435
""")
