import socket
import subprocess
import sys
import threading
import time

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from api.routes import router
from core.paths import static_dir

if sys.platform == "win32" and getattr(sys, "frozen", False):
    # Sem console próprio (console=False), subprocessos herdados (ex. pytesseract)
    # abririam janelas de console piscando; força CREATE_NO_WINDOW em todos.
    _orig_popen_init = subprocess.Popen.__init__

    def _no_window_init(self, *args, **kwargs):
        kwargs["creationflags"] = kwargs.get("creationflags", 0) | subprocess.CREATE_NO_WINDOW
        _orig_popen_init(self, *args, **kwargs)

    subprocess.Popen.__init__ = _no_window_init


def create_app() -> FastAPI:
    app = FastAPI(title="Routrip")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(router, prefix="/api")
    sd = static_dir()
    if sd.is_dir() and (sd / "index.html").is_file():
        app.mount("/", StaticFiles(directory=str(sd), html=True), name="static")
    return app


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wait_ready(port: int, timeout: float = 15.0) -> bool:
    import httpx

    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            if httpx.get(f"http://127.0.0.1:{port}/api/health", timeout=1.0).status_code == 200:
                return True
        except httpx.HTTPError:
            time.sleep(0.2)
    return False


def main() -> None:
    import webview

    port = _find_free_port()
    server = uvicorn.Server(uvicorn.Config(
        create_app(), host="127.0.0.1", port=port, log_level="warning",
    ))
    threading.Thread(target=server.run, daemon=True).start()
    if not _wait_ready(port):
        raise SystemExit("O servidor interno não iniciou a tempo.")

    webview.create_window(
        "Routrip",
        f"http://127.0.0.1:{port}/",
        width=1440,
        height=900,
        min_size=(1100, 700),
    )
    try:
        webview.start()
    except Exception:
        import ctypes

        ctypes.windll.user32.MessageBoxW(
            None,
            "Não foi possível abrir a janela do aplicativo.\n\n"
            "Verifique se o Microsoft Edge WebView2 Runtime está instalado:\n"
            "https://developer.microsoft.com/microsoft-edge/webview2/",
            "Routrip",
            0x10,
        )
        raise
    finally:
        server.should_exit = True


if __name__ == "__main__":
    main()
