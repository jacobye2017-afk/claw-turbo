"""Tests for the regex routing engine."""

import tempfile
import textwrap
from pathlib import Path

import pytest

from claw_turbo.config import load_routes
from claw_turbo.router import Router


@pytest.fixture
def routes_yaml(tmp_path):
    """Create a temporary routes.yaml for testing."""
    content = textwrap.dedent("""\
        routes:
          - name: print-container-all
            description: "打印柜号全部资料"
            patterns:
              - '打印\\s*(?P<container>[A-Z]{4}\\d{7})\\s*(的)?\\s*(资料|全部|所有)'
              - 'print\\s+(?P<container>[A-Z]{4}\\d{7})'
            command: 'bash /tmp/test.sh "{{raw_message}}"'
            response_template: "已执行打印 {{container}} 全部资料"

          - name: print-container-packing
            description: "只打印 packing list"
            patterns:
              - '(?:只)?打印\\s*(?P<container>[A-Z]{4}\\d{7})\\s*(的)?\\s*packing\\s*list'
            command: 'bash /tmp/test.sh "{{raw_message}}"'
            response_template: "已执行打印 {{container}} 的 Packing List"

          - name: print-container-mark
            description: "只打印柜号唛头"
            patterns:
              - '(?:只)?打印\\s*(?P<container>[A-Z]{4}\\d{7})\\s*(的)?\\s*(柜号)?\\s*(唛头|嘜头|mark)'
            command: 'bash /tmp/test.sh "{{raw_message}}"'
            response_template: "已执行打印 {{container}} 的柜号唛头"
    """)
    p = tmp_path / "routes.yaml"
    p.write_text(content, encoding="utf-8")
    return p


@pytest.fixture
def router(routes_yaml):
    return Router(routes_yaml)


class TestRouteLoading:
    def test_load_routes(self, routes_yaml):
        routes = load_routes(routes_yaml)
        assert len(routes) == 3
        assert routes[0].name == "print-container-all"

    def test_route_has_compiled_patterns(self, routes_yaml):
        routes = load_routes(routes_yaml)
        assert len(routes[0].patterns) == 2


class TestRouterMatch:
    def test_match_chinese_print_all(self, router):
        result = router.match("打印 GCXU5439046 资料")
        assert result is not None
        assert result.route.name == "print-container-all"
        assert result.captures["container"] == "GCXU5439046"

    def test_match_english_print(self, router):
        result = router.match("print GCXU5439046")
        assert result is not None
        assert result.route.name == "print-container-all"
        assert result.captures["container"] == "GCXU5439046"

    def test_match_packing_list(self, router):
        result = router.match("打印 OOCU8552373 的 packing list")
        assert result is not None
        assert result.route.name == "print-container-packing"

    def test_match_mark(self, router):
        result = router.match("只打印 OOCU8552373 的唛头")
        assert result is not None
        assert result.route.name == "print-container-mark"

    def test_match_mark_variant(self, router):
        result = router.match("只打印 OOCU8552373 的柜号唛头")
        assert result is not None
        assert result.route.name == "print-container-mark"

    def test_no_match(self, router):
        result = router.match("今天天气怎么样")
        assert result is None

    def test_no_match_partial_container(self, router):
        result = router.match("打印 GCX543 资料")
        assert result is None

    def test_match_time_under_1ms(self, router):
        result = router.match("打印 GCXU5439046 资料")
        assert result is not None
        assert result.match_time_us < 1000  # < 1ms


class TestTemplateRendering:
    def test_rendered_command(self, router):
        result = router.match("打印 GCXU5439046 资料")
        assert "打印 GCXU5439046 资料" in result.rendered_command
        assert "bash /tmp/test.sh" in result.rendered_command

    def test_rendered_response(self, router):
        result = router.match("打印 GCXU5439046 资料")
        assert "GCXU5439046" in result.rendered_response
        assert "已执行打印" in result.rendered_response

    def test_raw_message_in_command(self, router):
        msg = "打印 GCXU5439046 的全部资料"
        result = router.match(msg)
        assert msg in result.rendered_command


class TestHotReload:
    def test_reload_updates_routes(self, tmp_path):
        # Start with one route
        content = textwrap.dedent("""\
            routes:
              - name: route-a
                description: "test"
                patterns: ['test_a']
                command: 'echo a'
                response_template: "a"
        """)
        p = tmp_path / "routes.yaml"
        p.write_text(content, encoding="utf-8")

        router = Router(p)
        assert len(router.routes) == 1
        assert router.match("test_a") is not None

        # Update with two routes
        content2 = textwrap.dedent("""\
            routes:
              - name: route-a
                description: "test"
                patterns: ['test_a']
                command: 'echo a'
                response_template: "a"
              - name: route-b
                description: "test"
                patterns: ['test_b']
                command: 'echo b'
                response_template: "b"
        """)
        p.write_text(content2, encoding="utf-8")
        router._reload()
        assert len(router.routes) == 2
        assert router.match("test_b") is not None
