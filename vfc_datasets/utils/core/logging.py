import logging
import os
from datetime import datetime
from pathlib import Path


def setup_logging(
    script_name: str | None = None,
    level: int | None = None,
) -> str | None:
    if level is None:
        level = logging.getLevelNamesMapping()[os.getenv("LOG_LEVEL", "INFO").upper()]

    logging.root.handlers.clear()
    logging.root.setLevel(level)

    console_handler = logging.StreamHandler()
    console_handler.setLevel(level)
    console_handler.setFormatter(
        logging.Formatter("[%(asctime)s] %(levelname)s [%(name)s] %(message)s")
    )
    logging.root.addHandler(console_handler)

    log_file = None
    if script_name:
        log_dir = Path(os.getenv("DATA_PATH", ".data")) / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_file = str(log_dir / f"{script_name}_{timestamp}.log")

        file_handler = logging.FileHandler(log_file, mode="w")
        file_handler.setLevel(level)
        file_handler.setFormatter(
            logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
        )
        logging.root.addHandler(file_handler)
        logging.info("Logging to file: %s", log_file)

    return log_file
