import time
import logging
from fastapi import FastAPI, Request
from backend.app.modules.playlist.router import router as playlist_router
from backend.app.core.logger import setup_logging

# Initialize standard logging
setup_logging()
logger = logging.getLogger(__name__)

app = FastAPI(
    title="VibeFm API",
    description="AI Personal Radio Station Backend API",
    version="1.0.0"
)

# Startup ping - you will see this in the terminal instantly!
logger.debug("✅ Debugger is attached and running!")
logger.info("🚀 VibeFm application successfully loaded into memory!")

# Request logging middleware
@app.middleware("http")
async def log_requests(request: Request, call_next):
    start_time = time.time()
    
    logger.info(f"--> {request.method} {request.url.path}")
    
    try:
        response = await call_next(request)
        process_time = (time.time() - start_time) * 1000
        logger.info(
            f"<-- {request.method} {request.url.path} "
            f"[{response.status_code}] "
            f"({process_time:.2f}ms)"
        )
        return response
    except Exception as e:
        process_time = (time.time() - start_time) * 1000
        logger.error(
            f"<-- {request.method} {request.url.path} "
            f"[FAILED: {e.__class__.__name__}] "
            f"({process_time:.2f}ms)"
        )
        raise

# Include the playlist module router
app.include_router(playlist_router)

@app.get("/")
def read_root():
    return {"status": "ok", "message": "Welcome to VibeFm Radio API"}
