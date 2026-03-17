"""
Configuration centralisée du logging pour l'application.
Lit LOG_LEVEL et LOG_FILE depuis os.environ. Ne configure le logger racine qu'une seule fois.
"""
import logging
import os
import sys

_ROOT_LOGGER_CONFIGURED = False


def setup_logging():
    """Configure le logger racine : niveau, format, console (stderr), optionnellement fichier."""
    global _ROOT_LOGGER_CONFIGURED
    if _ROOT_LOGGER_CONFIGURED:
        return
    _ROOT_LOGGER_CONFIGURED = True

    level_name = os.environ.get("LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)

    log_format = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    date_format = "%Y-%m-%d %H:%M:%S"
    formatter = logging.Formatter(log_format, datefmt=date_format)

    root = logging.getLogger()
    root.setLevel(level)
    # Éviter double handlers si le module est réimporté
    if root.handlers:
        return
    console = logging.StreamHandler(sys.stderr)
    console.setFormatter(formatter)
    root.addHandler(console)

    log_file = os.environ.get("LOG_FILE", "").strip()
    if log_file:
        try:
            log_dir = os.path.dirname(log_file)
            if log_dir:
                os.makedirs(log_dir, exist_ok=True)
            file_handler = logging.FileHandler(log_file, mode="a", encoding="utf-8")
            file_handler.setFormatter(formatter)
            root.addHandler(file_handler)
        except OSError:
            root.warning("Could not create log file %s", log_file)
