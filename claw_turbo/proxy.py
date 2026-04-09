"""HTTP proxy mode: sits between OpenClaw gateway and Ollama, intercepts matched messages."""

import json
import logging
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.request import Request, urlopen
from urllib.error import URLError

from .router import Router
from .executor import execute

logger = logging.getLogger("claw-turbo")


class ProxyHandler(BaseHTTPRequestHandler):
    """Intercepts Ollama chat/generate API calls, routes matched messages directly."""

    router: Router = None  # set by serve()
    ollama_url: str = "http://127.0.0.1:11434"

    def log_message(self, format, *args):
        logger.debug(format, *args)

    def do_POST(self):
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length)

        # Try to intercept chat completions
        if self.path in ("/api/chat", "/v1/chat/completions", "/api/generate"):
            try:
                data = json.loads(body)
                user_message = self._extract_user_message(data)
                if user_message:
                    match = self.router.match(user_message)
                    if match:
                        logger.info("INTERCEPTED: %s -> %s", user_message[:60], match.route.name)
                        exec_result = execute(match)
                        response_text = match.rendered_response
                        if not exec_result.success:
                            response_text = f"命令执行失败: {exec_result.stderr[:200]}"
                        self._send_intercepted_response(data, response_text)
                        return
            except (json.JSONDecodeError, KeyError):
                pass

        # Passthrough to Ollama
        self._proxy_to_ollama(body)

    def do_GET(self):
        self._proxy_to_ollama(None)

    def _extract_user_message(self, data: dict) -> str | None:
        """Extract the last user message from chat API request."""
        # Ollama /api/chat format
        messages = data.get("messages", [])
        for msg in reversed(messages):
            if msg.get("role") == "user":
                return msg.get("content", "")

        # Ollama /api/generate format
        prompt = data.get("prompt")
        if prompt:
            return prompt

        return None

    def _send_intercepted_response(self, original_data: dict, response_text: str):
        """Send a synthetic response mimicking Ollama's format."""
        model = original_data.get("model", "claw-turbo")

        if self.path == "/api/chat":
            response = {
                "model": model,
                "message": {"role": "assistant", "content": response_text},
                "done": True,
                "done_reason": "stop",
                "total_duration": 0,
                "eval_count": 0,
            }
        elif self.path == "/v1/chat/completions":
            response = {
                "id": "claw-turbo-intercept",
                "object": "chat.completion",
                "model": model,
                "choices": [{
                    "index": 0,
                    "message": {"role": "assistant", "content": response_text},
                    "finish_reason": "stop",
                }],
                "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
            }
        else:  # /api/generate
            response = {
                "model": model,
                "response": response_text,
                "done": True,
                "done_reason": "stop",
                "total_duration": 0,
            }

        body = json.dumps(response, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _proxy_to_ollama(self, body: bytes | None):
        """Forward request to the real Ollama instance."""
        url = f"{self.ollama_url}{self.path}"
        try:
            req = Request(url, data=body, method=self.command)
            # Copy headers
            for key, val in self.headers.items():
                if key.lower() not in ("host", "content-length"):
                    req.add_header(key, val)

            with urlopen(req, timeout=300) as resp:
                resp_body = resp.read()
                self.send_response(resp.status)
                for key, val in resp.getheaders():
                    if key.lower() not in ("transfer-encoding",):
                        self.send_header(key, val)
                self.end_headers()
                self.wfile.write(resp_body)
        except URLError as e:
            logger.error("Failed to proxy to Ollama: %s", e)
            self.send_error(502, f"Ollama unreachable: {e}")


def serve(router: Router, host: str = "127.0.0.1", port: int = 11435,
          ollama_url: str = "http://127.0.0.1:11434"):
    """Start the proxy server."""
    ProxyHandler.router = router
    ProxyHandler.ollama_url = ollama_url

    server = HTTPServer((host, port), ProxyHandler)
    logger.info("claw-turbo proxy listening on %s:%d", host, port)
    logger.info("Proxying unmatched requests to %s", ollama_url)
    logger.info("Configure OpenClaw to point to http://%s:%d", host, port)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("Shutting down proxy")
        server.shutdown()
