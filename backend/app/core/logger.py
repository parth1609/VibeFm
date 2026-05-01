import logging
import sys

def setup_logging():
    """
    Configures application-wide logging formats.
    """
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s | %(levelname)-7s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[logging.StreamHandler(sys.stdout)],
        force=True,  # This tells Python to override Uvicorn's default loggers so we actually see these!
    )

    # Dial down noisy third-party libraries so our custom request logs stand out
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)

# Expose a default logger for this file if needed
logger = logging.getLogger(__name__)
