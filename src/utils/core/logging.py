import logging
import os
from datetime import datetime
from pathlib import Path

from config import BASE_DATA_PATH


def setup_logging(
    script_name: str | None = None,
    console_level: int | None = None,
    file_level: int | None = None,
) -> str | None:
    # Read environment variables at call time
    env_log_level = os.getenv("LOG_LEVEL", "INFO").upper()
    env_log_file = os.getenv("LOG_FILE", "")
    env_log_dir = os.getenv("LOG_DIR", str(BASE_DATA_PATH / "logs"))

    # Parse log level from env var
    level_map = {
        "DEBUG": logging.DEBUG,
        "INFO": logging.INFO,
        "WARNING": logging.WARNING,
        "ERROR": logging.ERROR,
        "CRITICAL": logging.CRITICAL,
    }
    default_level = level_map.get(env_log_level, logging.INFO)

    console_level = console_level or default_level
    file_level = file_level or logging.DEBUG

    # Clear existing handlers
    logging.root.handlers.clear()
    logging.root.setLevel(logging.DEBUG)

    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(console_level)
    console_handler.setFormatter(
        logging.Formatter("[%(asctime)s] %(levelname)s [%(name)s] %(message)s")
    )
    logging.root.addHandler(console_handler)

    # File handler (optional)
    log_file = None
    if env_log_file or script_name:
        Path(env_log_dir).mkdir(parents=True, exist_ok=True)

        if env_log_file:
            log_file = env_log_file
        else:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            log_file = str(Path(env_log_dir) / f"{script_name}_{timestamp}.log")

        file_handler = logging.FileHandler(log_file, mode="w")
        file_handler.setLevel(file_level)
        file_handler.setFormatter(
            logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
        )
        logging.root.addHandler(file_handler)
        logging.info("Logging to file: %s", log_file)

    return log_file
