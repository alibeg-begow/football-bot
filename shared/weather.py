import logging
from datetime import datetime, timezone
from shared.http_client import get_data

logger = logging.getLogger("weather")
BASE = "https://api.open-meteo.com/v1/forecast"

WMO_CODES = {
    0: "clear", 1: "mostly clear", 2: "partly cloudy", 3: "overcast",
    45: "fog", 48: "depositing rime fog",
    51: "light drizzle", 53: "drizzle", 55: "heavy drizzle",
    56: "light freezing drizzle", 57: "freezing drizzle",
    61: "light rain", 63: "rain", 65: "heavy rain",
    66: "light freezing rain", 67: "heavy freezing rain",
    71: "light snow", 73: "snow", 75: "heavy snow", 77: "snow grains",
    80: "light rain showers", 81: "rain showers", 82: "heavy rain showers",
    85: "light snow showers", 86: "heavy snow showers",
    95: "thunderstorm", 96: "thunderstorm with light hail", 99: "thunderstorm with heavy hail",
}

def get_weather(lat, lon, start_timestamp_utc):
    # get weather forecast for match time
    if lat is None or lon is None or not start_timestamp_utc:
        return None

    match_time = datetime.fromtimestamp(start_timestamp_utc, tz=timezone.utc)
    diff_days = (match_time - datetime.now(timezone.utc)).total_seconds() / 86400
    
    if diff_days < -1 or diff_days > 15:
        return None

    url = (
        f"{BASE}?latitude={lat}&longitude={lon}"
        f"&hourly=temperature_2m,relative_humidity_2m,precipitation,"
        f"precipitation_probability,wind_speed_10m,weather_code"
        f"&forecast_days=16&timezone=UTC"
    )

    data = get_data(url)
    if not data or not isinstance(data, dict):
        return None

    hourly = data.get("hourly") or {}
    times = hourly.get("time") or []
    if not times:
        return None

    target = match_time.strftime("%Y-%m-%dT%H:00")
    idx = None
    
    try:
        idx = times.index(target)
    except ValueError:
        min_diff = None
        for i, t in enumerate(times):
            try:
                td = datetime.strptime(t, "%Y-%m-%dT%H:%M").replace(tzinfo=timezone.utc)
            except ValueError:
                continue
            diff = abs((td - match_time).total_seconds())
            if min_diff is None or diff < min_diff:
                min_diff = diff
                idx = i
                
        if idx is None or (min_diff or 0) > 3 * 3600:
            return None

    def get_val(key):
        arr = hourly.get(key) or []
        return arr[idx] if idx < len(arr) else None

    code = get_val("weather_code")
    temp = get_val("temperature_2m")
    wind = get_val("wind_speed_10m")
    precip_prob = get_val("precipitation_probability")
    precip = get_val("precipitation")

    weather_data = {
        "temp_c": temp,
        "humidity_percent": get_val("relative_humidity_2m"),
        "precip_mm": precip,
        "precip_prob_percent": precip_prob,
        "wind_kmh": wind,
        "condition": WMO_CODES.get(code, "unknown") if code is not None else "unknown",
    }

    effects = []
    if isinstance(precip_prob, (int, float)) and precip_prob >= 60:
        effects.append("high rain probability: slippery pitch, mistakes and fouls may increase")
    if isinstance(wind, (int, float)) and wind >= 30:
        effects.append("strong wind: long passes accuracy drops, expected goals decrease")
    if isinstance(temp, (int, float)):
        if temp >= 30:
            effects.append("extreme heat: tempo drops, fatigue in second half")
        elif temp <= 2:
            effects.append("very cold: ball control becomes difficult")
    if isinstance(code, int) and code in (71, 73, 75, 77, 85, 86):
        effects.append("snow: game tempo and expected goals drop significantly")

    weather_data["game_impact"] = effects if effects else ["normal conditions, no significant impact expected"]
    return weather_data
