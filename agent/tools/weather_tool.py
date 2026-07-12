"""
agent/tools/weather_tool.py — Weather information tool using Open-Meteo (Free, no API key needed).
Geocoding: nominatim (openstreetmap). Weather: open-meteo.com
"""

import requests
from langchain_core.tools import tool


def _geocode(location: str) -> tuple[float, float, str]:
    """Location name → (lat, lon, display_name)"""
    url = "https://nominatim.openstreetmap.org/search"
    resp = requests.get(url, params={"q": location, "format": "json", "limit": 1},
                        headers={"User-Agent": "Aayie-Assistant/1.0"}, timeout=10)
    resp.raise_for_status()
    data = resp.json()
    if not data:
        raise ValueError(f"Location '{location}' nahi mila.")
    item = data[0]
    return float(item["lat"]), float(item["lon"]), item["display_name"]


def _wmo_description(code: int) -> str:
    """WMO weather code → human readable string."""
    codes = {
        0: "Clear sky ☀️", 1: "Mainly clear 🌤", 2: "Partly cloudy ⛅", 3: "Overcast ☁️",
        45: "Foggy 🌫", 48: "Icy fog 🌫",
        51: "Light drizzle 🌦", 53: "Moderate drizzle 🌦", 55: "Dense drizzle 🌧",
        61: "Slight rain 🌧", 63: "Moderate rain 🌧", 65: "Heavy rain 🌧",
        71: "Slight snow 🌨", 73: "Moderate snow 🌨", 75: "Heavy snow ❄️",
        80: "Light showers 🌦", 81: "Moderate showers 🌧", 82: "Violent showers ⛈",
        95: "Thunderstorm ⛈", 96: "Thunderstorm with hail ⛈", 99: "Thunderstorm with heavy hail ⛈",
    }
    return codes.get(code, f"Weather code {code}")


def get_weather(location: str) -> str:
    """Gets the current weather and 3-day forecast for a given location.
    
    Args:
        location (str): The name of the city, region, or place to get weather for (e.g. "Delhi", "New York").
    """
    try:
        lat, lon, display_name = _geocode(location)
        
        url = "https://api.open-meteo.com/v1/forecast"
        params = {
            "latitude": lat,
            "longitude": lon,
            "current": "temperature_2m,relative_humidity_2m,windspeed_10m,weathercode",
            "daily": "temperature_2m_max,temperature_2m_min,precipitation_probability_max,weathercode",
            "timezone": "Asia/Kolkata",
            "forecast_days": 3,
        }
        resp = requests.get(url, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        
        current = data["current"]
        daily   = data["daily"]
        
        temp     = current["temperature_2m"]
        humidity = current["relative_humidity_2m"]
        wind     = current["windspeed_10m"]
        wcode    = current["weathercode"]
        condition = _wmo_description(wcode)
        
        lines = [
            f"📍 Location: {display_name.split(',')[0]}",
            f"🌡  Temperature: {temp}°C",
            f"💧 Humidity: {humidity}%",
            f"💨 Wind Speed: {wind} km/h",
            f"🌤 Condition: {condition}",
            "",
            "📅 Next 3 Days Forecast:",
        ]
        for i in range(min(3, len(daily["time"]))):
            day_cond = _wmo_description(daily["weathercode"][i])
            lines.append(
                f"  {daily['time'][i]}  |  "
                f"Max: {daily['temperature_2m_max'][i]}°C  "
                f"Min: {daily['temperature_2m_min'][i]}°C  "
                f"Rain: {daily['precipitation_probability_max'][i]}%  "
                f"{day_cond}"
            )
        
        return "\n".join(lines)
    
    except Exception as e:
        return f"❌ Weather fetch nahi ho paya: {e}"
