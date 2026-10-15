"""A local Decisions endpoint for SDK and CLI integration tests; no paid calls."""

import json
import threading
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace

import pytest

import agentic_staff


def choice_answer(name, label, confidence=0.95):
    return {
        "type": "choice",
        "name": name,
        "choice": label,
        "confidence": confidence,
        "probabilities": [{"value": label, "probability": confidence}],
    }


def predicate_answer(name, score):
    return {"type": "predicate", "name": name, "probability": score}


def decision_body(answers):
    return {
        "model": agentic_staff.DECISION_MODEL,
        "answers": answers,
        "usage": {
            "input_tokens": 1,
            "input_tokens_details": {"cached_tokens": 0, "cache_write_tokens": 0},
            "output_tokens": 0,
            "output_tokens_details": {"reasoning_tokens": 0},
            "total_tokens": 1,
        },
    }


@pytest.fixture
def decision_api(monkeypatch):
    requests, responses = [], deque()

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            requests.append({"path": self.path, "body": payload})
            status, body = responses.popleft() if responses else (500, {"error": "No fixture"})
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(body).encode())

        def log_message(self, *_):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_port}/v1"
    monkeypatch.setenv("OPENAI_API_KEY", "local-test-key")
    monkeypatch.setenv("OPENAI_BASE_URL", base_url)
    monkeypatch.setattr(agentic_staff, "load_env", lambda: None)
    try:
        yield SimpleNamespace(
            base_url=base_url,
            requests=requests,
            responses=responses,
            enqueue=lambda *answers: responses.append((200, decision_body(list(answers)))),
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
