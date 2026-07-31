import sys
import os
import logging
from datetime import datetime

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

# add project root to sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from shared.db import get_connection
from shared.telegraph import create_analysis_page
from telegram_bot.keyboards import (
    day_selection_keyboard,
    match_list_keyboard,
    post_analysis_keyboard,
)

logger = logging.getLogger("telegram_bot")

def get_message_summary(text: str, num_lines: int = 6) -> str:
    # get first few lines for telegraph preview
    lines = [s for s in text.split("\n") if s.strip()]
    summary = "\n".join(lines[:num_lines])
    if len(lines) > num_lines:
        summary += "\n\n_...click the button below to read the full analysis._"
    return summary

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # show welcome message and day selection
    await update.message.reply_text(
        "*Football Analysis Bot*\n\n"
        "Which day's matches would you like to see?",
        reply_markup=day_selection_keyboard(),
        parse_mode="Markdown",
    )

async def day_selected_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # handle day selection
    query = update.callback_query
    await query.answer()

    day = query.data.replace("day_", "") 

    keyboard, total, target = match_list_keyboard(day, page=0)
    day_str = "Today" if day == "today" else "Tomorrow"

    if total == 0:
        msg = (
            f"*{day_str}* ({target})\n\n"
            "No analyzed matches available right now.\n\n"
            "_Note: If a match is not listed here, its analysis may still be in progress._"
        )
    else:
        msg = (
            f"*{day_str}* ({target}) - {total} matches\n\n"
            "Select a match for detailed analysis:\n\n"
            "_Note: If a match is not listed here, its analysis may still be in progress._"
        )

    await query.edit_message_text(
        text=msg,
        reply_markup=keyboard,
        parse_mode="Markdown",
    )

async def pagination_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # handle list pagination
    query = update.callback_query
    await query.answer()

    parts = query.data.split("_")
    day = parts[1]
    page = int(parts[2])

    keyboard, total, target = match_list_keyboard(day, page)
    day_str = "Today" if day == "today" else "Tomorrow"

    if total == 0:
        msg = (
            f"*{day_str}* ({target})\n\n"
            "No analyzed matches available right now.\n\n"
            "_Note: If a match is not listed here, its analysis may still be in progress._"
        )
    else:
        msg = (
            f"*{day_str}* ({target}) - {total} matches\n\n"
            "Select a match for detailed analysis:"
        )

    await query.edit_message_text(
        text=msg,
        reply_markup=keyboard,
        parse_mode="Markdown",
    )

async def match_selected_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # show match analysis
    query = update.callback_query
    await query.answer()

    match_id = int(query.data.replace("match_", ""))

    from telegram_bot.keyboards import get_target_date

    conn = get_connection()
    cursor = conn.cursor()

    # get match info
    cursor.execute("SELECT * FROM matches WHERE match_id = ?", (match_id,))
    match = cursor.fetchone()

    if not match:
        conn.close()
        await query.edit_message_text(
            "Match not found.",
            reply_markup=day_selection_keyboard(),
        )
        return

    today_date = get_target_date("today")
    day = "today" if match["match_date"] == today_date else "tomorrow"

    # get analysis
    cursor.execute(
        "SELECT analysis_text FROM match_analysis WHERE match_id = ?", (match_id,)
    )
    analysis_row = cursor.fetchone()
    conn.close()

    if not analysis_row:
        await query.edit_message_text(
            "Analysis for this match is not ready yet.",
            reply_markup=post_analysis_keyboard(day),
        )
        return

    match_title = f"{match['home_team']} vs {match['away_team']} - {match['league_name']}"
    header = (
        f"*{match['home_team']} vs {match['away_team']}*\n"
        f"{match['match_time']} | {match['league_name']} | {match['match_date']}\n\n"
    )

    analysis_text = analysis_row["analysis_text"]
    full_message = header + analysis_text

    # send directly if short enough
    if len(full_message) <= 4000:
        await query.edit_message_text(
            text=full_message,
            reply_markup=post_analysis_keyboard(day),
            parse_mode="Markdown",
        )
        return

    # use telegraph for long messages
    telegraph_url = create_analysis_page(match_title, full_message)

    if telegraph_url:
        summary = get_message_summary(analysis_text)
        msg = header + summary

        main_menu_btn = InlineKeyboardButton("Main Menu", callback_data="home")
        back_btn = InlineKeyboardButton("Match List", callback_data=f"day_{day}")
        read_btn = InlineKeyboardButton("Read Full Analysis", url=telegraph_url)

        kb = InlineKeyboardMarkup([
            [read_btn],
            [back_btn, main_menu_btn],
        ])

        await query.edit_message_text(
            text=msg,
            reply_markup=kb,
            parse_mode="Markdown",
        )
    else:
        # fallback if telegraph fails
        chunks = []
        text = full_message
        while len(text) > 4000:
            cut = text.rfind("\n", 0, 4000)
            if cut == -1:
                cut = 4000
            chunks.append(text[:cut])
            text = text[cut:]
        chunks.append(text)

        await query.edit_message_text(text=chunks[0], parse_mode="Markdown")
        for i, chunk in enumerate(chunks[1:], 1):
            kb = post_analysis_keyboard(day) if i == len(chunks) - 1 else None
            await query.message.reply_text(text=chunk, reply_markup=kb, parse_mode="Markdown")

async def main_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # return to main menu
    query = update.callback_query
    await query.answer()

    await query.edit_message_text(
        "*Football Analysis Bot*\n\n"
        "Which day's matches would you like to see?",
        reply_markup=day_selection_keyboard(),
        parse_mode="Markdown",
    )
