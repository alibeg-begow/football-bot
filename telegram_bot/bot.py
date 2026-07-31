import sys
import os
import logging

# add project root to sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
)

from shared.config_loader import TELEGRAM_BOT_TOKEN
from shared.db import init_db
from telegram_bot.handlers import (
    start_command,
    day_selected_callback,
    pagination_callback,
    match_selected_callback,
    main_menu_callback,
)

# setup logging
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG_DIR = os.path.join(PROJECT_ROOT, "logs")
os.makedirs(LOG_DIR, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(os.path.join(LOG_DIR, "bot.log"), encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger("telegram_bot")

def main():
    # start the bot
    if not TELEGRAM_BOT_TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN is missing in .env")
        return

    # create db tables
    init_db()

    logger.info("Initializing bot application...")

    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    # add handlers
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CallbackQueryHandler(day_selected_callback, pattern="^day_"))
    app.add_handler(CallbackQueryHandler(pagination_callback, pattern="^list_"))
    app.add_handler(CallbackQueryHandler(match_selected_callback, pattern="^match_"))
    app.add_handler(CallbackQueryHandler(main_menu_callback, pattern="^home$"))

    # run bot
    logger.info("Bot is polling for messages...")
    app.run_polling()

if __name__ == "__main__":
    main()
