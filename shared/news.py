import logging
from datetime import datetime, timedelta
from urllib.parse import quote
from email.utils import parsedate_to_datetime
import feedparser

from shared.http_client import get_text
from shared.config_loader import CONFIG

logger = logging.getLogger("news")

TIMEZONE = CONFIG["timezone"]
SCANDAL_KEYWORDS = CONFIG.get("scandal_keywords", [])
INJURY_KEYWORDS = CONFIG.get(
    "injury_keywords",
    ["injury", "injured", "doubt", "out for", "surgery", "treatment", "missing", "sidelined"],
)

QUERY_TEMPLATES = [
    "{team} injury",
    "{team} starting lineup",
    "{team} suspension",
]

def fetch_rss(query, lang="en", country="US", days=7, limit=8):
    # fetch a single google news rss query
    if lang == "tr":
        url = (f"https://news.google.com/rss/search?q={quote(query)}"
               f"&hl=tr&gl=TR&ceid=TR:tr")
    else:
        url = (f"https://news.google.com/rss/search?q={quote(query)}"
               f"&hl=en-US&gl=US&ceid=US:en")

    xml_text = get_text(url)
    if not xml_text:
        return []

    try:
        feed = feedparser.parse(xml_text)
    except Exception as e:
        logger.debug(f"RSS parse error: {e}")
        return []

    now = datetime.now()
    limit_date = now - timedelta(days=days)

    news_list = []
    for entry in feed.entries[:limit * 2]:
        try:
            date_str = ""
            pub = entry.get("published")
            if pub:
                try:
                    pd = parsedate_to_datetime(pub)
                    if pd.tzinfo is not None:
                        pd = pd.replace(tzinfo=None)
                    if pd < limit_date:
                        continue
                    date_str = pd.strftime("%d.%m.%Y")
                except (TypeError, ValueError):
                    pass

            title = entry.get("title", "").strip()
            if not title:
                continue

            news_list.append({
                "title": title,
                "date": date_str,
                "source": (entry.get("source", {}) or {}).get("title", "Google News"),
            })
            if len(news_list) >= limit:
                break
        except Exception:
            continue

    return news_list

def tag_news(news_item):
    # add importance tags to news for ai engine
    title = (news_item.get("title") or "").lower()
    news_item["scandal"] = any(k in title for k in SCANDAL_KEYWORDS)
    news_item["injury"] = any(k in title for k in INJURY_KEYWORDS)
    news_item["important"] = news_item["scandal"] or news_item["injury"]
    return news_item

def get_team_news(team_name, espn_slug=None, limit=10):
    # fetch targeted news for a team from multiple sources
    all_news = []
    seen = set()

    def add_news(news_list):
        for h in news_list:
            key = (h.get("title") or "")[:60].lower()
            if key and key not in seen:
                seen.add(key)
                all_news.append(tag_news(h))

    for template in QUERY_TEMPLATES:
        add_news(fetch_rss(template.format(team=team_name), lang="en", limit=5))

    if espn_slug:
        try:
            from shared import espn
            add_news(espn.get_team_news(espn_slug, team_name, limit=4))
        except Exception as e:
            logger.debug(f"ESPN news error: {e}")

    # sort by importance
    all_news.sort(key=lambda h: (not h.get("important", False),))
    return all_news[:limit]
