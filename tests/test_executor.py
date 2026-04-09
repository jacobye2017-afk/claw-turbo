"""Tests for the bash command executor."""

import textwrap
from pathlib import Path

import pytest

from claw_turbo.router import Router
from claw_turbo.executor import execute


@pytest.fixture
def routes_yaml(tmp_path):
    content = textwrap.dedent("""\
        routes:
          - name: echo-test
            description: "echo test"
            patterns:
              - 'echo\\s+(?P<word>\\w+)'
            command: 'echo "hello {{word}}"'
            response_template: "Said hello to {{word}}"

          - name: fail-test
            description: "always fail"
            patterns:
              - 'fail_now'
            command: 'exit 1'
            response_template: "Should not see this"
    """)
    p = tmp_path / "routes.yaml"
    p.write_text(content, encoding="utf-8")
    return p


@pytest.fixture
def router(routes_yaml):
    return Router(routes_yaml)


class TestExecutor:
    def test_successful_execution(self, router):
        match = router.match("echo world")
        assert match is not None
        result = execute(match)
        assert result.success is True
        assert result.return_code == 0
        assert "hello world" in result.stdout

    def test_failed_execution(self, router):
        match = router.match("fail_now")
        assert match is not None
        result = execute(match)
        assert result.success is False
        assert result.return_code == 1

    def test_timeout(self, router):
        # Override command to sleep
        match = router.match("echo world")
        assert match is not None
        # Use a very short timeout to test timeout handling
        match.route.command = "sleep 10"
        result = execute(match, timeout=1)
        assert result.success is False
        assert "timed out" in result.stderr

    def test_command_template_rendering(self, router):
        match = router.match("echo world")
        assert match is not None
        assert match.rendered_command == 'echo "hello world"'

    def test_response_template_rendering(self, router):
        match = router.match("echo world")
        assert match is not None
        assert match.rendered_response == "Said hello to world"
