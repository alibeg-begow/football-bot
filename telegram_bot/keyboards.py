import sys
import os
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

# add project root to sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from shared.db import get_connection
from shared.config_loader import CONFIG

TZ = ZoneInfo(CONFIG["timezone"])
PER_PAGE = CONFIG["matches_per_page"]


def get_target_date(day):
    # get date for today or tomorrow
    today = datetime.now(TZ)
    if day == "tomorrow":
        target = today + timedelta(days=1)
    else:
        target = today
    return target.strftime("%d.%m.%Y")


def day_selection_keyboard():
    # main menu keyboard
    keyboard = [
        [
            InlineKeyboardButton("Today", callback_data="day_today"),
            InlineKeyboardButton("Tomorrow", callback_data="day_tomorrow"),
        ]
    ]
    return InlineKeyboardMarkup(keyboard)


def match_list_keyboard(day, page=0):
    # list matches for the selected day
    target_date = get_target_date(day)

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """SELECT m.match_id, m.home_team, m.away_team,
                  m.match_time, m.league_name
           FROM matches m
           JOIN match_analysis ma ON m.match_id = ma.match_id
           WHERE m.match_date = ?
           ORDER BY m.match_time ASC""",
        (target_date,),
    )
    all_matches = cursor.fetchall()
    conn.close()

    total = len(all_matches)
    total_pages = max(1, (total + PER_PAGE - 1) // PER_PAGE)

    # check bounds
    if page < 0:
        page = 0
    if page >= total_pages:
        page = total_pages - 1

    # get matches for current page
    start = page * PER_PAGE
    end = start + PER_PAGE
    page_matches = all_matches[start:end]

    keyboard = []

    # create buttons for each match
    for match in page_matches:
        btn_text = f"{match['home_team']} vs {match['away_team']} | {match['match_time']} | {match['league_name']}"
        # limit text length for telegram
        if len(btn_text) > 64:
            btn_text = btn_text[:61] + "..."
        keyboard.append(
            [InlineKeyboardButton(btn_text, callback_data=f"match_{match['match_id']}")]
        )

    # pagination buttons
    nav_buttons = []
    if page > 0:
        nav_buttons.append(
            InlineKeyboardButton("Prev", callback_data=f"list_{day}_{page - 1}")
        )
    if page < total_pages - 1:
        nav_buttons.append(
            InlineKeyboardButton("Next", callback_data=f"list_{day}_{page + 1}")
        )
    if nav_buttons:
        keyboard.append(nav_buttons)

    # main menu button
    keyboard.append(
        [InlineKeyboardButton("Main Menu", callback_data="home")]
    )

    return InlineKeyboardMarkup(keyboard), total, target_date


def post_analysis_keyboard(day):
    # back button after reading analysis
    keyboard = [
        [InlineKeyboardButton("Back to Match List", callback_data=f"list_{day}_0")]
    ]
    return InlineKeyboardMarkup(keyboard)
