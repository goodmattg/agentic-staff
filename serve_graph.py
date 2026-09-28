"""Serve one generated diagram on loopback; exit after an hour without requests."""

import sys
import time
from functools import partial
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path

IDLE_SECONDS = 3600


class DiagramHandler(SimpleHTTPRequestHandler):
    def log_message(self, format, *args):
        pass


def main():
    directory = Path(sys.argv[1]).resolve()
    handler = partial(DiagramHandler, directory=str(directory))
    with HTTPServer(("127.0.0.1", 0), handler) as server:
        server.timeout = IDLE_SECONDS
        print(f"http://127.0.0.1:{server.server_port}/workflow.html", flush=True)
        while True:
            started = time.monotonic()
            server.handle_request()
            if time.monotonic() - started >= IDLE_SECONDS:
                break


if __name__ == "__main__":
    main()
