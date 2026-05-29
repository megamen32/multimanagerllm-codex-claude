#!/usr/bin/env python3
"""MultiManager v2 — .app bundle entry point."""
import sys, os

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from multimanager.handler import Handler
from multimanager.settings import MASTER_SKILLS
from multimanager.menubar import setup_menubar
import socket, threading, webbrowser
from http.server import ThreadingHTTPServer


def free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0)); return s.getsockname()[1]


def main():
    port = free_port()
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"[mm] http://127.0.0.1:{port}")
    MASTER_SKILLS.mkdir(parents=True, exist_ok=True)
    setup_menubar(port)
    threading.Timer(0.35, lambda: webbrowser.open(f"http://127.0.0.1:{port}")).start()
    try: server.serve_forever()
    except KeyboardInterrupt: server.shutdown()


if __name__ == "__main__":
    main()
