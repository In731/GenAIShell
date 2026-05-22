import logging
from logging.handlers import RotatingFileHandler
import sys
from pathlib import Path
from rich.logging import RichHandler
from config.settings import settings

def setup_logger(name: str = "terminal_assistant") -> logging.Logger:
    """Configures a double-handler logger.
    
    1. RichHandler for beautiful, human-readable terminal output.
    2. RotatingFileHandler to write trace logs to a local file.
    """
    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, settings.log_level.upper(), logging.INFO))
    
    # Avoid duplicate handlers if setup is called multiple times
    if logger.handlers:
        return logger

    # Ensure log directories exist
    settings.log_file.parent.mkdir(parents=True, exist_ok=True)
    
    # 1. Create file handler (writes detailed trace files)
    file_formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s"
    )
    file_handler = RotatingFileHandler(
        settings.log_file,
        maxBytes=10 * 1024 * 1024,  # 10MB
        backupCount=5,
        encoding="utf-8"
    )
    file_handler.setFormatter(file_formatter)
    file_handler.setLevel(logging.DEBUG)  # Always log details to file
    
    # 2. Create Console Rich Handler (gorgeous CLI messages)
    console_handler = RichHandler(
        rich_tracebacks=True,
        markup=True,
        show_path=False,
        omit_repeated_times=True
    )
    console_handler.setLevel(getattr(logging, settings.log_level.upper(), logging.INFO))
    
    # Attach handlers
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    
    # Prevent propagation to root logger
    logger.propagate = False
    
    return logger

# Export standard global logger
logger = setup_logger()
