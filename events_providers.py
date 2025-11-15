# events_providers.py
import os
from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional
import requests
from urllib.parse import urlencode
from dotenv import load_dotenv
import math

load_dotenv()  # loads .env if present

@dataclass
class Event:
    title: str
    description: str
    start_time: datetime
    end_time: Optional[datetime]
    venue_name: str
    address: str
    lat: Optional[float]
    lng: Optional[float]
    url: str
    source: str  # e.g. "Eventbrite", "Meetup", "Campus"


def haversine_km(lat1, lon1, lat2, lon2):
    """Distance between two lat/lon points in km."""
    R = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = (math.sin(dphi / 2)**2 +
         math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2)**2)
    return 2 * R * math.asin(math.sqrt(a))


# ---------- Eventbrite example provider (API-based) ----------

def fetch_eventbrite_events(
    lat: float,
    lng: float,
    radius_km: float,
    start_date: datetime,
    end_date: datetime
) -> List[Event]:
    """
    Fetch events from Eventbrite using their API.
    NOTE: You must supply EVENTBRITE_TOKEN in your .env file.
    This is example code; check Eventbrite's latest docs for exact params.
    """
    token = os.getenv("EVENTBRITE_TOKEN")
    if not token:
        # No token configured; return empty list to avoid runtime errors.
        return []

    url = "https://www.eventbriteapi.com/v3/events/search/"
    params = {
        "location.latitude": lat,
        "location.longitude": lng,
        "location.within": f"{radius_km}km",
        "start_date.range_start": start_date.isoformat() + "Z",
        "start_date.range_end": end_date.isoformat() + "Z",
        "expand": "venue",
    }
    headers = {"Authorization": f"Bearer {token}"}
    resp = requests.get(url, headers=headers, params=params, timeout=10)
    resp.raise_for_status()
    data = resp.json()

    events: List[Event] = []
    for item in data.get("events", []):
        try:
            name = item.get("name", {}).get("text") or "Untitled Event"
            description = (item.get("description", {}) or {}).get("text") or ""
            start = datetime.fromisoformat(item["start"]["utc"].replace("Z", "+00:00"))
            end = None
            if item.get("end") and item["end"].get("utc"):
                end = datetime.fromisoformat(item["end"]["utc"].replace("Z", "+00:00"))

            venue = item.get("venue", {}) or {}
            venue_name = venue.get("name") or "Unknown venue"
            address_parts = []
            addr = venue.get("address", {}) or {}
            for key in ["address_1", "city", "region", "postal_code", "country"]:
                if addr.get(key):
                    address_parts.append(addr[key])
            address = ", ".join(address_parts)
            ev_lat = float(venue["latitude"]) if venue.get("latitude") else None
            ev_lng = float(venue["longitude"]) if venue.get("longitude") else None

            url_evt = item.get("url") or ""
            events.append(
                Event(
                    title=name,
                    description=description,
                    start_time=start,
                    end_time=end,
                    venue_name=venue_name,
                    address=address,
                    lat=ev_lat,
                    lng=ev_lng,
                    url=url_evt,
                    source="Eventbrite",
                )
            )
        except Exception:
            # Be robust to partial data.
            continue
    return events


# ---------- Example HTML "scraper" provider (campus site) ----------

from bs4 import BeautifulSoup  # pip install beautifulsoup4

def fetch_campus_events(
    start_date: datetime,
    end_date: datetime
) -> List[Event]:
    """
    Example: scrape a campus events HTML page.
    Replace CAMPUS_EVENTS_URL with your real URL.
    Make sure you're allowed to scrape it (check robots.txt & ToS).
    """
    url = os.getenv("CAMPUS_EVENTS_URL")
    if not url:
        return []

    resp = requests.get(url, timeout=10)
    resp.raise_for_status()
    html = resp.text
    soup = BeautifulSoup(html, "html.parser")

    events: List[Event] = []
    # This will depend on the actual HTML of your campus events page.
    # Here we assume each event is inside <div class="event-item">.
    for div in soup.select(".event-item"):
        try:
            title_tag = div.select_one(".event-title")
            date_tag = div.select_one(".event-date")
            venue_tag = div.select_one(".event-venue")
            link_tag = div.select_one("a")

            title = title_tag.get_text(strip=True) if title_tag else "Untitled event"
            date_str = date_tag.get_text(strip=True) if date_tag else ""
            venue_name = venue_tag.get_text(strip=True) if venue_tag else "On campus"
            url_evt = link_tag["href"] if link_tag and link_tag.has_attr("href") else url

            # You will need a proper date parser here.
            # For hackathon: assume date_str is "YYYY-MM-DD HH:MM".
            start = datetime.fromisoformat(date_str)

            if not (start_date <= start <= end_date):
                continue

            events.append(
                Event(
                    title=title,
                    description="Campus event",
                    start_time=start,
                    end_time=None,
                    venue_name=venue_name,
                    address=venue_name,
                    lat=None,
                    lng=None,
                    url=url_evt,
                    source="Campus",
                )
            )
        except Exception:
            continue

    return events


# ---------- Merge & deduplicate ----------

def merge_and_dedupe(events_lists: List[List[Event]]) -> List[Event]:
    """
    Deduplicate by (title, date, venue) signature.
    """
    sigs = set()
    merged: List[Event] = []
    for lst in events_lists:
        for e in lst:
            date_key = e.start_time.date().isoformat()
            sig = (e.title.lower(), date_key, e.venue_name.lower())
            if sig not in sigs:
                sigs.add(sig)
                merged.append(e)
    # Sort by start time
    merged.sort(key=lambda e: e.start_time)
    return merged


def get_events_for_query(
    lat: float,
    lng: float,
    radius_km: float,
    start_date: datetime,
    end_date: datetime
) -> List[Event]:
    """
    Main orchestration: call providers, combine, filter.
    """
    events_from_eventbrite = fetch_eventbrite_events(lat, lng, radius_km, start_date, end_date)
    campus_events = fetch_campus_events(start_date, end_date)

    events = merge_and_dedupe([
        events_from_eventbrite,
        campus_events
    ])

    # If some sources don't support radius, optionally filter by radius here
    filtered: List[Event] = []
    for e in events:
        if e.lat is not None and e.lng is not None:
            if haversine_km(lat, lng, e.lat, e.lng) <= radius_km:
                filtered.append(e)
        else:
            # If no geo, keep it (or choose to drop; you decide)
            filtered.append(e)

    return filtered
