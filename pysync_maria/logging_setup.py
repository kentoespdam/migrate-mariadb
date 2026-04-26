import logging
import logging.handlers
import sys
import threading
from pathlib import Path
from typing import Any

LOG_DIR = Path("logs")

def setup_logging():
    """
    Configure root logger with two RotatingFileHandlers (info + error)
    and attach global exception hooks.
    """
    LOG_DIR.mkdir(exist_ok=True)
    
    info_log = LOG_DIR / "pysync.log"
    error_log = LOG_DIR / "error.log"
    
    # Detailed format for log entries
    log_format = (
        "%(asctime)s [%(levelname)s] %(name)s [%(threadName)s] "
        "%(module)s:%(lineno)d :: %(message)s"
    )
    formatter = logging.Formatter(log_format)
    
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    
    # Clear existing handlers if any (to avoid duplicates during re-setup)
    root_logger.handlers.clear()
    
    # Info Handler (pysync.log)
    info_handler = logging.handlers.RotatingFileHandler(
        info_log, maxBytes=5*1024*1024, backupCount=5, encoding="utf-8"
    )
    info_handler.setLevel(logging.INFO)
    info_handler.setFormatter(formatter)
    root_logger.addHandler(info_handler)
    
    # Error Handler (error.log)
    error_handler = logging.handlers.RotatingFileHandler(
        error_log, maxBytes=5*1024*1024, backupCount=5, encoding="utf-8"
    )
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(formatter)
    root_logger.addHandler(error_handler)
    
    # Attach global exception hooks
    sys.excepthook = _handle_uncaught
    threading.excepthook = _handle_thread_exc
    
    logging.getLogger("pysync_maria.bootstrap").info("Logging system initialized")

def _handle_uncaught(exc_type, exc_value, exc_traceback):
    """Hook for sys.excepthook."""
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return
    
    logging.getLogger("pysync_maria.uncaught").critical(
        "Uncaught exception", exc_info=(exc_type, exc_value, exc_traceback)
    )

def _handle_thread_exc(args):
    """Hook for threading.excepthook."""
    logging.getLogger("pysync_maria.uncaught.thread").critical(
        f"Uncaught thread exception in {args.thread.name}", 
        exc_info=(args.exc_type, args.exc_value, args.exc_traceback)
    )

def attach_asyncio_handler(loop: Any):
    """
    Attach a custom exception handler to an asyncio loop.
    Should be called when the loop is available (e.g. app.on_mount).
    """
    def handler(loop, context):
        msg = context.get("message")
        exception = context.get("exception")
        future = context.get("future")
        
        ctx_data = {}
        if future:
             ctx_data["future"] = str(future)
             
        logging.getLogger("pysync_maria.uncaught.asyncio").error(
            f"Asyncio error: {msg}", 
            extra={"context": ctx_data},
            exc_info=exception
        )
    
    loop.set_exception_handler(handler)

def log_exception(logger: logging.Logger, msg: str, exc: BaseException | None = None, **context):
    """
    Helper to log an exception with standardized context formatting.
    """
    if context:
        msg = f"{msg} | ctx={context}"
    
    # exc_info=exc or True will capture the current exception info if exc is None
    logger.error(msg, exc_info=exc if exc is not None else True)
