import logging
import sys

logger = logging.getLogger("utcp")

if not logger.hasHandlers():  # Only add default handler if user didn't configure logging
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(filename)s:%(lineno)d - %(message)s"))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
