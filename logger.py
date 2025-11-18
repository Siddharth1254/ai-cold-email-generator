import logging
import os
from logging.handlers import RotatingFileHandler


LOG_DIR = "logs"
LOG_FILE = os.path.join(LOG_DIR, "app.log")

os.makedirs(LOG_DIR, exist_ok=True)

logger = logging.getLogger("ai_cold_email_generator")
if not logger.handlers:
	logger.setLevel(logging.INFO)

	formatter = logging.Formatter(
		"%(asctime)s | %(levelname)s | %(name)s | %(message)s"
	)

	file_handler = RotatingFileHandler(LOG_FILE, maxBytes=1_000_000, backupCount=3)
	file_handler.setFormatter(formatter)

	console_handler = logging.StreamHandler()
	console_handler.setFormatter(formatter)

	logger.addHandler(file_handler)
	logger.addHandler(console_handler)
	logger.propagate = False


