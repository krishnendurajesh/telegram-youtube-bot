import os
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
OPENCLAW_BASE_URL = os.getenv("OPENCLAW_BASE_URL")
OPENCLAW_MODEL = os.getenv("OPENCLAW_MODEL")
