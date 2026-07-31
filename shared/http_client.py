import time
import json
import logging
import threading
from urllib.parse import urlencode
import requests

from shared.config_loader import (
    CONFIG,
    SCRAPER_API_KEY,
)
FLARESOLVERR_URL = None

logger = logging.getLogger("http_client")

try:
    from curl_cffi import requests as curl_requests
    CURL_CFFI_VAR = True
except ImportError:
    CURL_CFFI_VAR = False
    logger.warning("curl_cffi not installed")

IMPERSONATE_LIST = ["chrome124", "chrome120", "chrome116", "safari17_0", "edge101"]

_cache = {}
_cache_lock = threading.Lock()
_last_request_time = [0.0]
_request_lock = threading.Lock()

STATS = {
    "free": 0,
    "flaresolverr": 0,
    "scrapingant": 0,
    "scraperapi": 0,
    "cache": 0,
    "failed": 0,
}

MIN_INTERVAL = CONFIG.get("min_request_interval_seconds", 0.4)
TIMEOUT = CONFIG.get("request_timeout_seconds", 30)

def _wait():
    # prevent spamming requests
    with _request_lock:
        elapsed = time.time() - _last_request_time[0]
        if elapsed < MIN_INTERVAL:
            time.sleep(MIN_INTERVAL - elapsed)
        _last_request_time[0] = time.time()

def _try_free(url, expect_json=True):
    # try direct request with curl_cffi or requests
    if CURL_CFFI_VAR:
        for imp in IMPERSONATE_LIST:
            try:
                _wait()
                r = curl_requests.get(url, impersonate=imp, timeout=TIMEOUT)
                if r.status_code == 200:
                    STATS["free"] += 1
                    if expect_json:
                        try:
                            return r.json(), True
                        except Exception:
                            return r.text, True
                    return r.text, True
                if r.status_code in (400, 404):
                    logger.debug(f"Not found [{r.status_code}]: {url}")
                    return None, True
                logger.debug(f"Free route blocked [{r.status_code}] ({imp}): {url}")
            except Exception as e:
                logger.debug(f"Free request error ({imp}): {type(e).__name__}")
                continue
    else:
        # fallback to standard requests
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        try:
            _wait()
            r = requests.get(url, headers=headers, timeout=TIMEOUT)
            if r.status_code == 200:
                STATS["free"] += 1
                if expect_json:
                    try:
                        return r.json(), True
                    except Exception:
                        return r.text, True
                return r.text, True
            if r.status_code in (400, 404):
                return None, True
        except Exception as e:
            logger.debug(f"Requests fallback error: {e}")

    return None, False

def _try_flaresolverr(url, expect_json=True):
    # try flaresolverr local docker
    if not FLARESOLVERR_URL:
        return None

    payload = {
        "cmd": "request.get",
        "url": url,
        "maxTimeout": 60000,
    }

    try:
        _wait()
        r = requests.post(
            FLARESOLVERR_URL,
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=70,
        )
        if r.status_code != 200:
            logger.debug(f"FlareSolverr no response [{r.status_code}]: {url}")
            return None

        data = r.json()
        if data.get("status") != "ok":
            logger.debug(f"FlareSolverr error: {data.get('message', 'Unknown error')}")
            return None

        solution = data.get("solution", {})
        response_text = solution.get("response", "")
        http_status = solution.get("status", 0)

        if http_status in (400, 404):
            logger.debug(f"FlareSolverr: not found [{http_status}]: {url}")
            return None

        if not response_text:
            return None

        STATS["flaresolverr"] += 1

        if expect_json:
            try:
                return json.loads(response_text)
            except (ValueError, TypeError):
                return response_text
        return response_text

    except requests.exceptions.ConnectionError:
        logger.debug("FlareSolverr connection error — is docker running?")
        return None
    except Exception as e:
        logger.debug(f"FlareSolverr error: {type(e).__name__}: {e}")
        return None

def _try_scrapingant(url, expect_json=True):
    return None

    from urllib.parse import quote_plus
    encoded_url = quote_plus(url)
    proxy_url = (
        f"https://api.scrapingant.com/v2/general"
        f"?url={encoded_url}"
        f"&x-api-key={SCRAPINGANT_API_KEY}"
        f"&browser=true"
        f"&return_page_source=true"
    )

    try:
        _wait()
        r = requests.get(proxy_url, timeout=90)
        if r.status_code not in (200, 201):
            logger.debug(f"ScrapingAnt [{r.status_code}]: {url}")
            return None

        text = r.text
        if not text:
            return None

        if expect_json:
            import json as _json
            try:
                parsed = _json.loads(text)
                if isinstance(parsed, dict) and list(parsed.keys()) == ["error"]:
                    logger.debug(f"ScrapingAnt API error: {parsed}")
                    return None
                STATS["scrapingant"] += 1
                return parsed
            except Exception:
                pass
            return None

        STATS["scrapingant"] += 1
        return text
    except Exception as e:
        logger.debug(f"ScrapingAnt error: {e}")
        return None

def _try_scraperapi(url, expect_json=True):
    # try scraper api as last resort
    if not SCRAPER_API_KEY:
        logger.debug("SCRAPER_API_KEY missing, skipping fallback.")
        return None

    payload = {"api_key": SCRAPER_API_KEY, "url": url}
    proxy_url = "http://api.scraperapi.com/?" + urlencode(payload)

    try:
        _wait()
        r = requests.get(proxy_url, timeout=70)
        if r.status_code != 200:
            logger.debug(f"ScraperAPI [{r.status_code}]: {url}")
            return None
        STATS["scraperapi"] += 1
        if expect_json:
            try:
                return r.json()
            except ValueError:
                return r.text
        return r.text
    except Exception as e:
        logger.debug(f"ScraperAPI error: {e}")
        return None

def get_data(url, expect_json=True, use_cache=True):
    # main entry to fetch data using waterfall strategy
    key = (url, expect_json)
    if use_cache:
        with _cache_lock:
            if key in _cache:
                STATS["cache"] += 1
                return _cache[key]

    result, final = _try_free(url, expect_json)

    if result is None and not final:
        result = _try_flaresolverr(url, expect_json)
        if result is not None:
            final = True

    if result is None and not final:
        result = _try_scrapingant(url, expect_json)
        if result is not None:
            final = True

    if result is None and not final:
        result = _try_scraperapi(url, expect_json)

    if result is None:
        STATS["failed"] += 1

    if use_cache and result is not None:
        with _cache_lock:
            _cache[key] = result

    return result

def get_text(url):
    # helper for text fetching
    return get_data(url, expect_json=False)

def print_stats():
    # log request statistics
    total = (
        STATS["free"]
        + STATS["flaresolverr"]
        + STATS["scrapingant"]
        + STATS["scraperapi"]
    )
    logger.info(
        f"HTTP STATS | Total: {total} | "
        f"Free: {STATS['free']} | "
        f"FlareSolverr: {STATS['flaresolverr']} | "
        f"ScrapingAnt: {STATS['scrapingant']} | "
        f"ScraperAPI: {STATS['scraperapi']} | "
        f"Cache: {STATS['cache']} | "
        f"Failed: {STATS['failed']}"
    )
    if total:
        free_total = STATS["free"] + STATS["flaresolverr"] + STATS["scrapingant"]
        rate = 100.0 * free_total / total
        logger.info(f"Free Request Success Rate: %{rate:.1f}")
