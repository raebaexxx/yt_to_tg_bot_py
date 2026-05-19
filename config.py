import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
MAX_FILE_SIZE_MB = int(os.getenv("MAX_FILE_SIZE_MB", "1900"))
MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024
DOWNLOAD_DIR = os.getenv("DOWNLOAD_DIR", "./downloads")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

os.makedirs(DOWNLOAD_DIR, exist_ok=True)
