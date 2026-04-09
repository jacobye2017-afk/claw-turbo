"""Configuration loader with hot-reload support for routes.yaml."""

import logging
import os
import re
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

import yaml

logger = logging.getLogger("claw-turbo")

DEFAULT_ROUTES_PATH = Path(__file__).parent.parent / "routes.yaml"


@dataclass
class Route:
    name: str
    description: str
    patterns: list[re.Pattern]
    command: str
    response_template: str

    # Store raw pattern strings for display
    raw_patterns: list[str] = field(default_factory=list)


def _compile_patterns(raw_patterns: list[str]) -> list[re.Pattern]:
    compiled = []
    for p in raw_patterns:
        compiled.append(re.compile(p, re.IGNORECASE))
    return compiled


def load_routes(path: Path | str) -> list[Route]:
    """Load and compile routes from a YAML file."""
    path = Path(path)
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    routes = []
    for entry in data.get("routes", []):
        route = Route(
            name=entry["name"],
            description=entry.get("description", ""),
            patterns=_compile_patterns(entry["patterns"]),
            command=entry["command"],
            response_template=entry.get("response_template", ""),
            raw_patterns=entry["patterns"],
        )
        routes.append(route)
    logger.info("Loaded %d routes from %s", len(routes), path)
    return routes


class ConfigWatcher:
    """Watches routes.yaml for changes and triggers reload."""

    def __init__(self, path: Path | str, on_reload: callable, interval: float = 1.0):
        self._path = Path(path)
        self._on_reload = on_reload
        self._interval = interval
        self._mtime: float = 0
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self):
        self._mtime = self._get_mtime()
        self._thread = threading.Thread(target=self._watch, daemon=True)
        self._thread.start()
        logger.info("Config watcher started for %s", self._path)

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2)

    def _get_mtime(self) -> float:
        try:
            return os.path.getmtime(self._path)
        except OSError:
            return 0

    def _watch(self):
        while not self._stop.is_set():
            self._stop.wait(self._interval)
            new_mtime = self._get_mtime()
            if new_mtime > self._mtime:
                self._mtime = new_mtime
                logger.info("Detected change in %s, reloading...", self._path)
                try:
                    self._on_reload()
                except Exception:
                    logger.exception("Failed to reload config")
