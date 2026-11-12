"""Start KaupBudget.

    python run.py                 # desktop: opens the app in its own window
    python run.py --browser       # desktop, but in your web browser
    python run.py --server        # EC2 / server mode: listens on 0.0.0.0:8000

On a server, set KAUP_PASSWORD so nobody else can open your budget.
"""
import argparse
import socket
import sys
import threading
import time
import webbrowser
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import uvicorn  # noqa: E402


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wait_until_up(port: int, timeout: float = 15) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                return
        except OSError:
            time.sleep(0.1)


def main():
    ap = argparse.ArgumentParser(description="Run KaupBudget")
    ap.add_argument("--server", action="store_true", help="server mode (for EC2)")
    ap.add_argument("--browser", action="store_true", help="open in the web browser instead of an app window")
    ap.add_argument("--host", default=None)
    ap.add_argument("--port", type=int, default=None)
    args = ap.parse_args()

    from kaupbudget import config

    # Launched from the desktop icon there's no console; give logs somewhere to go.
    if sys.stdout is None or sys.stderr is None:
        config.DATA_DIR.mkdir(parents=True, exist_ok=True)
        log = open(config.DATA_DIR / "kaupbudget.log", "a", encoding="utf-8", buffering=1)
        sys.stdout = sys.stdout or log
        sys.stderr = sys.stderr or log

    from kaupbudget.server import app

    if args.server:
        host, port = args.host or "0.0.0.0", args.port or 8000
        if not config.PASSWORD:
            print("WARNING: KAUP_PASSWORD is not set - anyone who can reach this server can see your budget.")
        uvicorn.run(app, host=host, port=port)
        return

    host, port = args.host or "127.0.0.1", args.port or _free_port()
    server = uvicorn.Server(uvicorn.Config(app, host=host, port=port, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    _wait_until_up(port)
    url = f"http://{host}:{port}/"

    if not args.browser:
        try:
            import webview

            webview.create_window("KaupBudget", url, width=1280, height=860, min_size=(900, 600))
            webview.start()
            server.should_exit = True
            return
        except Exception as e:  # noqa: BLE001 - fall back to the browser if the window can't open
            print(f"App window unavailable ({e}); opening in your browser instead.")

    webbrowser.open(url)
    print(f"KaupBudget is running at {url}  (close this window to stop it)")
    try:
        thread.join()
    except KeyboardInterrupt:
        server.should_exit = True


if __name__ == "__main__":
    main()
