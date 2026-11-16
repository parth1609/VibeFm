import mimetypes
import time
import logging
from pathlib import Path

from starlette.types import ASGIApp, Receive, Scope, Send
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from .modules.playlist.router import router as playlist_router
from .modules.rj.router import router as rj_router
from .core.logger import setup_logging

# Initialize standard logging
setup_logging()
logger = logging.getLogger(__name__)

app = FastAPI(
    title="VibeFm API",
    description="AI Personal Radio Station Backend API",
    version="1.2.0"
)

# CORS — allow the Flutter app to call the backend from any origin (dev mode)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Raw ASGI logging middleware — does NOT use BaseHTTPMiddleware.
#
# BaseHTTPMiddleware wraps response body consumption in a background task
# that gets cancelled before StreamingResponse generators can finish.
# This raw ASGI middleware simply intercepts the response status without
# interfering with the byte flow, so audio streaming works correctly.
# ---------------------------------------------------------------------------

class RequestLoggingMiddleware:
    """Lightweight ASGI middleware that logs requests without breaking streams."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        method = scope.get("method", "?")
        path = scope.get("path", "/")
        start_time = time.time()
        status_code = 0

        async def _send_wrapper(message):
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message.get("status", 0)
                elapsed = (time.time() - start_time) * 1000
                logger.info(f"--> {method} {path}")
                logger.info(
                    f"<-- {method} {path} [{status_code}] ({elapsed:.1f}ms)"
                )
            await send(message)

        try:
            await self.app(scope, receive, _send_wrapper)
        except Exception as exc:
            elapsed = (time.time() - start_time) * 1000
            logger.error(
                f"<-- {method} {path} [FAILED: {exc.__class__.__name__}] "
                f"({elapsed:.1f}ms)"
            )
            raise


app.add_middleware(RequestLoggingMiddleware)


# Startup ping - you will see this in the terminal instantly!
logger.debug("✅ Debugger is attached and running!")
logger.info("🚀 VibeFm application successfully loaded into memory!")

# Include module routers
app.include_router(playlist_router)
app.include_router(rj_router)

@app.get("/health")
def health():
    return {"status": "ok", "version": app.version}


# ---------------------------------------------------------------------------
# Web app (Expo web export)
#
# Serving the exported bundle from the API means opening the deployed URL shows
# the radio itself instead of raw JSON. Everything stays on one origin, so the
# browser app talks to /playlist/* without CORS games.
#
# Rebuild the bundle after UI changes:
#   cd VibeFmExpo && npx expo export --platform web --output-dir ../web
# ---------------------------------------------------------------------------

# Explicit types so fonts/bundles are served correctly on every host platform
# (some mimetype tables do not know .ttf/.woff and fall back to text/plain).
for _suffix, _type in (
    (".ttf", "font/ttf"),
    (".otf", "font/otf"),
    (".woff", "font/woff"),
    (".woff2", "font/woff2"),
    (".js", "application/javascript"),
    (".webp", "image/webp"),
    (".ico", "image/x-icon"),
):
    mimetypes.add_type(_type, _suffix)

_WEB_DIR = Path(__file__).resolve().parents[2] / "web"

if _WEB_DIR.is_dir():
    # Mounted last, so /playlist/*, /docs and /health still win.
    app.mount("/", StaticFiles(directory=_WEB_DIR, html=True), name="web")
    logger.info("🌐 Serving web app from %s", _WEB_DIR)
else:

    @app.get("/")
    def read_root():
        return {"status": "ok", "message": "Welcome to VibeFm Radio API"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.app.app:app", host="0.0.0.0", port=8000, reload=True)
