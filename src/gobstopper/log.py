from loguru import logger
import sys

def custom_format(record):
    """Custom formatter that handles missing request_id"""
    request_id = record.get("extra", {}).get("request_id", "Gobstopper-SYS")
    
    format_string = (
        "<magenta>{time:YYYY-MM-DD HH:mm:ss.SSS}</magenta> | "
        "<level>{level: <8}</level> | "
        f"<yellow>{request_id}</yellow> | "
        "<blue>{name}</blue>:<cyan>{function}</cyan>:<green>{line}</green> - <level>{message}</level>\n"
    )
    return format_string

def setup_logging(level="DEBUG", sink=sys.stderr):
    """
    Set up Loguru logger with Gobstopper/Cyberpunk theme.
    """
    logger.remove()
    logger.add(sink, level=level, format=custom_format, enqueue=True)
    return logger

# Default logger
log = setup_logging()
