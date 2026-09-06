"""Wetter ueber Open-Meteo.

Kein API-Key noetig, beide Staedte in einem einzigen Request. Geliefert werden
genau die drei Werte, die der Entwurf braucht: Symbol, Hoechst- und Tiefstwert
je Tag.
"""

from __future__ import annotations

from datetime import date, datetime

from . import config, fetch, store

# WMO-Wettercodes. Die Symbole sind die Textvarianten aus dem Entwurf
# (Variation Selector 15), damit sie monochrom bleiben und nicht als
# farbiges Emoji gerendert werden.
SUN = "☀︎"        # Sonne
CLOUD = "☁︎"      # Wolke
RAIN = "☂︎"       # Schirm
SNOW = "❄︎"       # Schneeflocke
STORM = "⚡︎"      # Blitz
FOG = "≈"              # Nebel

_CODE_TABLE: list[tuple[range, str, str]] = [
    (range(0, 1), SUN, "klar"),
    (range(1, 3), SUN, "leicht bewölkt"),
    (range(3, 4), CLOUD, "bewölkt"),
    (range(45, 49), FOG, "Nebel"),
    (range(51, 58), RAIN, "Niesel"),
    (range(61, 66), RAIN, "Regen"),
    (range(66, 68), RAIN, "gefrierender Regen"),
    (range(71, 78), SNOW, "Schnee"),
    (range(80, 83), RAIN, "Schauer"),
    (range(85, 87), SNOW, "Schneeschauer"),
    (range(95, 100), STORM, "Gewitter"),
]

_WEEKDAYS = ["MO", "DI", "MI", "DO", "FR", "SA", "SO"]


def describe(code: int) -> tuple[str, str]:
    """WMO-Code -> (Symbol, Beschreibung). Jeder Code 0..99 trifft etwas."""
    for span, icon, label in _CODE_TABLE:
        if code in span:
            return icon, label
    # Luecken in der WMO-Tabelle (z. B. 4..44) konservativ als bewoelkt.
    return CLOUD, "wechselhaft"


def weekday_label(day: str) -> str:
    return _WEEKDAYS[date.fromisoformat(day).weekday()]


def refresh(conn, *, force: bool = False) -> dict[str, int]:
    """Holt die Vorhersage fuer alle konfigurierten Staedte."""
    stale = force or any(
        (store.weather_age_minutes(conn, city) or 1e9) > config.WEATHER_TTL_MINUTES
        for city in config.CITIES
    )
    if not stale:
        return {"cities": 0, "cached": len(config.CITIES)}

    names = list(config.CITIES)
    payload = fetch.fetch_json(
        config.OPEN_METEO_URL,
        {
            "latitude": ",".join(str(config.CITIES[c]["lat"]) for c in names),
            "longitude": ",".join(str(config.CITIES[c]["lon"]) for c in names),
            "daily": "weather_code,temperature_2m_max,temperature_2m_min,sunrise,sunset",
            "hourly": "temperature_2m,weather_code",
            "forecast_days": max(config.WEATHER_DAYS, 1),
            "timezone": config.TIMEZONE,
        },
    )
    if payload is None:
        return {"cities": 0, "error": 1}

    # Bei mehreren Koordinaten antwortet Open-Meteo mit einer Liste, bei einer
    # einzelnen mit einem Objekt.
    blocks = payload if isinstance(payload, list) else [payload]
    written = 0
    for city, block in zip(names, blocks):
        daily = block.get("daily") or {}
        days = daily.get("time") or []
        codes = daily.get("weather_code") or []
        highs = daily.get("temperature_2m_max") or []
        lows = daily.get("temperature_2m_min") or []
        sunrises = daily.get("sunrise") or []
        sunsets = daily.get("sunset") or []
        rows = [
            {
                "day": d,
                "code": int(c),
                "hi": float(hi),
                "lo": float(lo),
                "sunrise": sr[11:16] if sr else "",
                "sunset": ss[11:16] if ss else "",
            }
            for d, c, hi, lo, sr, ss in zip(
                days, codes, highs, lows,
                sunrises or [""] * len(days), sunsets or [""] * len(days),
            )
        ]
        if rows:
            store.save_weather(conn, city, rows)
            written += 1

        hourly = block.get("hourly") or {}
        hours = hourly.get("time") or []
        hour_codes = hourly.get("weather_code") or []
        temps = hourly.get("temperature_2m") or []
        hour_rows = [
            {"hour": h, "code": int(c), "temp": float(t)}
            for h, c, t in zip(hours, hour_codes, temps)
        ]
        if hour_rows:
            store.save_weather_hours(conn, city, hour_rows)
    return {"cities": written}


def board_payload(conn, city: str) -> dict:
    """Wetterdaten in der Form, die das Frontend erwartet."""
    if city not in config.CITIES:
        city = config.DEFAULT_CITY
    rows = store.load_weather(conn, city)
    today = datetime.now().date().isoformat()
    hour_rows = store.load_weather_hours(conn, city)
    by_day: dict[str, list] = {}
    for row in hour_rows:
        by_day.setdefault(row["hour"][:10], []).append(row)

    days = []
    for row in rows:
        icon, label = describe(row["code"])
        day_hours = by_day.get(row["day"]) or []
        hot = max(day_hours, key=lambda h: h["temp"], default=None)
        cold = min(day_hours, key=lambda h: h["temp"], default=None)
        days.append(
            {
                "day": "HEUTE" if row["day"] == today else weekday_label(row["day"]),
                "date": row["day"],
                "icon": icon,
                "label": label,
                "hi": round(row["hi"]),
                "lo": round(row["lo"]),
                "sunrise": row["sunrise"],
                "sunset": row["sunset"],
                "hot": {"time": hot["hour"][11:16], "temp": round(hot["temp"])} if hot else None,
                "cold": {"time": cold["hour"][11:16], "temp": round(cold["temp"])} if cold else None,
            }
        )
    now_hour = datetime.now().strftime("%Y-%m-%dT%H:00")
    hours = []
    for row in hour_rows:
        if not row["hour"].startswith(today):
            continue
        icon, label = describe(row["code"])
        hours.append(
            {
                "hour": row["hour"][11:16],
                "icon": icon,
                "label": label,
                "temp": round(row["temp"]),
                "isNow": row["hour"] == now_hour,
            }
        )
    return {
        "city": city,
        "cityLabel": city.upper(),
        "cities": list(config.CITIES),
        "days": days,
        "hours": hours,
    }
