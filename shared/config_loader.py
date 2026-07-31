import json
import os
from dotenv import load_dotenv

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# code
load_dotenv(os.path.join(PROJECT_ROOT, ".env"))

# code
with open(os.path.join(PROJECT_ROOT, "config.json"), "r", encoding="utf-8") as f:
    CONFIG = json.load(f)

# code
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
NVIDIA_API_KEY = os.getenv("NVIDIA_API_KEY", "")
SCRAPER_API_KEY = os.environ.get("SCRAPER_API_KEY", "")
