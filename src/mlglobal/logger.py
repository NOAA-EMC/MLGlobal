import logging

"""
Logger setup module for the mlglobal project.

This module configures the logging settings for the entire project using Python's built-in
logging module. It sets up a default logging format, date format, and log level, and provides
a logger instance named "mlglobal" for use throughout the project.

Functions
---------
setup_logger(level=logging.INFO, fmt="[%(asctime)s] %(levelname)8s - %(message)s", datefmt="%Y-%m-%dT%H:%M:%S")
    Configures the logging system with the specified log level, format, and date format.

Attributes
----------
logger : logging.Logger
"""


log = logging.getLogger()


def setup_logging(
    fmt: str = "[%(asctime)s] %(levelname)8s - %(message)s",
    datefmt: str = "%Y-%m-%dT%H:%M:%S",
    debug: bool = False,
):

    logger = logging.getLogger()
    for handler in logger.handlers:
        logger.removeHandler(handler)

    level = logging.DEBUG if debug else logging.INFO
    kwargs: dict = {"datefmt": datefmt, "format": fmt, "level": level}

    logging.basicConfig(**kwargs)
