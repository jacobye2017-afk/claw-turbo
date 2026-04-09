"""Core regex matching engine for routing user messages to skills."""

import logging
import re
import threading
import time
from dataclasses import dataclass
from pathlib import Path

from .config import ConfigWatcher, Route, load_routes

logger = logging.getLogger("claw-turbo")


@dataclass
class MatchResult:
    route: Route
    captures: dict[str, str]
    raw_message: str
    match_time_us: float  # microseconds

    @property
    def rendered_command(self) -> str:
        return _render_template(self.route.command, self._template_vars())

    @property
    def rendered_response(self) -> str:
        return _render_template(self.route.response_template, self._template_vars())

    def _template_vars(self) -> dict[str, str]:
        return {"raw_message": self.raw_message, **self.captures}


def _render_template(template: str, variables: dict[str, str]) -> str:
    """Replace {{key}} placeholders with values."""
    def replacer(m: re.Match) -> str:
        key = m.group(1).strip()
        return variables.get(key, m.group(0))
    return re.sub(r"\{\{(\s*\w+\s*)\}\}", replacer, template)


class Router:
    """Thread-safe regex router with hot-reload support."""

    def __init__(self, routes_path: Path | str | None = None, watch: bool = False):
        from .config import DEFAULT_ROUTES_PATH
        self._path = Path(routes_path) if routes_path else DEFAULT_ROUTES_PATH
        self._lock = threading.RLock()
        self._routes: list[Route] = load_routes(self._path)
        self._watcher: ConfigWatcher | None = None

        if watch:
            self._watcher = ConfigWatcher(self._path, self._reload)
            self._watcher.start()

    def _reload(self):
        new_routes = load_routes(self._path)
        with self._lock:
            self._routes = new_routes
        logger.info("Router reloaded with %d routes", len(new_routes))

    @property
    def routes(self) -> list[Route]:
        with self._lock:
            return list(self._routes)

    def match(self, message: str) -> MatchResult | None:
        """Try to match a message against all routes. Returns first match or None."""
        start = time.perf_counter()
        with self._lock:
            routes = list(self._routes)

        for route in routes:
            for pattern in route.patterns:
                m = pattern.search(message)
                if m:
                    elapsed_us = (time.perf_counter() - start) * 1_000_000
                    result = MatchResult(
                        route=route,
                        captures=m.groupdict(),
                        raw_message=message,
                        match_time_us=elapsed_us,
                    )
                    logger.info(
                        "MATCHED [%s] in %.1fus: %s",
                        route.name, elapsed_us, message[:80],
                    )
                    return result

        elapsed_us = (time.perf_counter() - start) * 1_000_000
        logger.debug("NO MATCH in %.1fus: %s", elapsed_us, message[:80])
        return None

    def stop(self):
        if self._watcher:
            self._watcher.stop()
