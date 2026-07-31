import requests
import logging
from urllib.parse import urlencode
from shared.config_loader import SCRAPER_API_KEY

logger = logging.getLogger("google_search")

def fetch_google_news(query):
    # use scraperapi autoparse to get google search results
    if not SCRAPER_API_KEY:
        logger.error("Search failed: API key missing")
        return "Internet search failed (missing API key)."

    payload = {
        'api_key': SCRAPER_API_KEY,
        'autoparse': 'true',
        'url': f'https://www.google.com/search?q={query}&hl=en'
    }

    try:
        response = requests.get("http://api.scraperapi.com/", params=payload, timeout=45)
        response.raise_for_status()
        data = response.json()
        
        results = []
        if 'organic_results' in data:
            for res in data['organic_results'][:4]:
                title = res.get('title', '')
                snippet = res.get('snippet', '')
                if title and snippet:
                    results.append(f"- {title}: {snippet}")
        
        if results:
            return "\n".join(results)
        else:
            return "No recent news found."
            
    except Exception as e:
        logger.error(f"Internet search error: {e}")
        return "Error occurred during internet search."
