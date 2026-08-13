import json
import re
import urllib.error
import urllib.request
from urllib.parse import urlencode

NOMINATIM_REVERSE = "https://nominatim.openstreetmap.org/reverse"
USER_AGENT = "NexgateAI/1.0 (coarse city geolocation)"
COORD_PATTERN = re.compile(r"-?\d+\.\d+")


def round_coarse(lat, lon, decimals=1):
    factor = 10**decimals
    return round(float(lat) * factor) / factor, round(float(lon) * factor) / factor


def format_city_label(address):
    if not isinstance(address, dict):
        return None
    state = (
        address.get("state")
        or address.get("province")
        or address.get("region")
        or ""
    ).strip()
    city = (
        address.get("city")
        or address.get("town")
        or address.get("village")
        or address.get("municipality")
        or address.get("county")
        or address.get("suburb")
        or ""
    ).strip()
    if state and city:
        if city.startswith(state) or state in city:
            return city[:120]
        return f"{state}{city}"[:120]
    label = city or state
    return label[:120] if label else None


def reverse_geocode_city(lat, lon):
    lat_r, lon_r = round_coarse(lat, lon)
    params = urlencode(
        {
            "lat": lat_r,
            "lon": lon_r,
            "format": "json",
            "zoom": 10,
            "addressdetails": 1,
        }
    )
    url = f"{NOMINATIM_REVERSE}?{params}"
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, json.JSONDecodeError, TimeoutError, ValueError):
        return None
    return format_city_label(payload.get("address"))


def sanitize_location_context(raw):
    text = (raw or "").strip()
    if not text or len(text) > 120:
        return None
    if COORD_PATTERN.search(text):
        return None
    return text
