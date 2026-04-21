import logging
from datetime import datetime

from vfc_datasets.config import LOG_DIR, LOG_LEVEL


def setup_logging(
    script_name: str | None = None,
    level: int | None = None,
) -> str | None:
    level = level if level is not None else LOG_LEVEL

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
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_file = str(LOG_DIR / f"{script_name}_{timestamp}.log")

        file_handler = logging.FileHandler(log_file, mode="w")
        file_handler.setLevel(level)
        file_handler.setFormatter(
            logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
        )
        logging.root.addHandler(file_handler)
        logging.info("Logging to file: %s", log_file)

    return log_file
