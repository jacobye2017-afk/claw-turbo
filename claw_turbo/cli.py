"""CLI entry point for claw-turbo."""

import argparse
import logging
import re
import sys
from pathlib import Path

from . import __version__
from .config import DEFAULT_ROUTES_PATH


def setup_logging(verbose: bool = False):
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )


def cmd_serve(args):
    """Start the HTTP proxy server."""
    from .router import Router
    from .proxy import serve

    setup_logging(args.verbose)
    router = Router(args.routes, watch=True)
    serve(router, host=args.host, port=args.port, ollama_url=args.ollama_url)


def cmd_test(args):
    """Test a message against route rules."""
    from .router import Router

    setup_logging(args.verbose)
    router = Router(args.routes)
    message = args.message

    match = router.match(message)
    if match:
        print(f"MATCHED: {match.route.name}")
        print(f"  Description: {match.route.description}")
        print(f"  Captures:    {match.captures}")
        print(f"  Command:     {match.rendered_command}")
        print(f"  Response:    {match.rendered_response}")
        print(f"  Match time:  {match.match_time_us:.1f}us")
    else:
        print("NO MATCH")
        print("Message did not match any route. It would be passed to LLM.")
        sys.exit(1)


def cmd_routes(args):
    """List all configured routes."""
    from .config import load_routes

    setup_logging(False)
    routes = load_routes(args.routes)

    print(f"Routes from: {args.routes}\n")
    for i, route in enumerate(routes, 1):
        print(f"  {i}. {route.name}")
        print(f"     {route.description}")
        for p in route.raw_patterns:
            print(f"     pattern: {p}")
        print(f"     command: {route.command[:80]}...")
        print()


def cmd_add_skill(args):
    """Auto-generate route rules from a SKILL.md file."""
    import yaml

    setup_logging(args.verbose)
    skill_path = Path(args.path)

    # Find SKILL.md
    if skill_path.is_dir():
        skill_md = skill_path / "SKILL.md"
    else:
        skill_md = skill_path

    if not skill_md.exists():
        print(f"Error: {skill_md} not found")
        sys.exit(1)

    content = skill_md.read_text(encoding="utf-8")

    # Extract skill name from frontmatter
    name_match = re.search(r"^name:\s*(.+)$", content, re.MULTILINE)
    skill_name = name_match.group(1).strip() if name_match else skill_md.parent.name

    # Find the scripts directory
    scripts_dir = skill_md.parent / "scripts"
    run_script = scripts_dir / "run.sh"

    if not run_script.exists():
        print(f"Warning: {run_script} not found")
        run_script_path = f"bash {skill_md.parent}/scripts/run.sh"
    else:
        run_script_path = f"bash {run_script}"

    # Extract trigger keywords from SKILL.md
    trigger_match = re.search(r'Triggers?\s+on:?\s*["\']?(.+?)["\']?\s*$', content, re.MULTILINE)
    triggers = trigger_match.group(1) if trigger_match else ""

    print(f"Skill: {skill_name}")
    print(f"Script: {run_script_path}")
    print(f"Triggers: {triggers}")
    print()

    # Generate a template route entry
    route_entry = {
        "name": skill_name,
        "description": f"Auto-generated from {skill_md}",
        "patterns": [
            f"(?i)(?:TODO_KEYWORD)\\s*(?P<param>\\S+)",
        ],
        "command": f'{run_script_path} "{{{{raw_message}}}}"',
        "response_template": f"Executed {skill_name}: {{{{param}}}}",
    }

    print("Generated route template (add to routes.yaml):\n")
    print("  - " + yaml.dump(route_entry, allow_unicode=True, default_flow_style=False).replace("\n", "\n    ").rstrip())
    print()
    print("NOTE: Edit the 'patterns' field to match your actual trigger patterns.")
    print(f"      Refer to triggers in SKILL.md: {triggers}")


def cmd_hook(args):
    """Run as OpenClaw pre-message hook."""
    from .hook import run_hook

    setup_logging(args.verbose)
    run_hook(args.routes)


def cmd_install(args):
    """Show hook installation instructions."""
    from .hook import install_hook

    install_hook()


def main():
    parser = argparse.ArgumentParser(
        prog="claw-turbo",
        description="Zero-latency skill routing middleware for OpenClaw",
    )
    parser.add_argument("--version", action="version", version=f"claw-turbo {__version__}")
    parser.add_argument("--routes", type=Path, default=DEFAULT_ROUTES_PATH,
                        help="Path to routes.yaml")
    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose logging")

    sub = parser.add_subparsers(dest="command")

    # serve
    p_serve = sub.add_parser("serve", help="Start HTTP proxy server")
    p_serve.add_argument("--host", default="127.0.0.1")
    p_serve.add_argument("--port", type=int, default=11435)
    p_serve.add_argument("--ollama-url", default="http://127.0.0.1:11434")
    p_serve.set_defaults(func=cmd_serve)

    # test
    p_test = sub.add_parser("test", help="Test a message against routes")
    p_test.add_argument("message", help="Message to test")
    p_test.set_defaults(func=cmd_test)

    # routes
    p_routes = sub.add_parser("routes", help="List all route rules")
    p_routes.set_defaults(func=cmd_routes)

    # add-skill
    p_add = sub.add_parser("add-skill", help="Generate route from SKILL.md")
    p_add.add_argument("path", help="Path to skill directory or SKILL.md")
    p_add.set_defaults(func=cmd_add_skill)

    # hook
    p_hook = sub.add_parser("hook", help="Run as OpenClaw pre-message hook (reads stdin)")
    p_hook.set_defaults(func=cmd_hook)

    # install
    p_install = sub.add_parser("install", help="Show hook installation instructions")
    p_install.set_defaults(func=cmd_install)

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(1)

    args.func(args)


if __name__ == "__main__":
    main()
