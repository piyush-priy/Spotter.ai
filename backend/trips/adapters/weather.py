"""
Weather forecast adapter.
Queries Open-Meteo for checkpoint coordinates and ETA arrival timestamps.
Units are normalized to mph for wind speed and inches/hour for precipitation.
"""
import math
import asyncio
import logging
from datetime import datetime
from typing import List, Dict, Any, Optional
import httpx

logger = logging.getLogger(__name__)


def _simulated_weather_fallback(
    latitude: float, longitude: float, eta_dt: datetime
) -> Dict[str, Any]:
    """
    Deterministic weather fallback if network is unreachable.
    Generates realistic weather based on coordinates and time.
    """
    # Deterministic pseudo-random variation based on lat/lon/hour
    hour = eta_dt.hour
    day = eta_dt.day
    seed = math.sin(latitude * 5.0) * math.cos(longitude * 3.0) + math.sin((hour + day) * 0.5)

    # Wind typically 8-38 mph, occasionally gusting higher in plains / mountain areas
    base_wind = 14.0 + 12.0 * math.sin(latitude * 2.0 + longitude * 0.5)
    wind_mph = max(4.0, round(base_wind + 8.0 * seed, 1))

    # Precipitation chances
    precip_factor = math.cos(latitude * 4.0 - longitude * 2.0 + hour)
    if precip_factor > 0.65:
        rain_in_hr = round((precip_factor - 0.65) * 0.8, 2)
        snow_in_hr = 0.0
    elif precip_factor < -0.75 and latitude > 38.0:
        rain_in_hr = 0.0
        snow_in_hr = round(abs(precip_factor + 0.75) * 2.5, 2)
    else:
        rain_in_hr = 0.0
        snow_in_hr = 0.0

    return {
        "wind_mph": wind_mph,
        "rain_in_hr": rain_in_hr,
        "snow_in_hr": snow_in_hr,
        "forecast_timestamp": eta_dt.isoformat(),
        "source": "simulated_forecast",
        "quality": "ESTIMATED",
    }


async def fetch_checkpoint_weather(
    latitude: float,
    longitude: float,
    eta_iso: str,
    client: httpx.AsyncClient,
    semaphore: asyncio.Semaphore,
) -> Dict[str, Any]:
    """
    Fetch weather for a single checkpoint from Open-Meteo at its ETA arrival timestamp.
    """
    try:
        eta_dt = datetime.fromisoformat(eta_iso)
    except Exception:
        eta_dt = datetime.now()

    # Open-Meteo URL
    url = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": latitude,
        "longitude": longitude,
        "hourly": "wind_speed_10m,precipitation,rain,snowfall",
        "wind_speed_unit": "mph",
        "precipitation_unit": "inch",
        "forecast_days": 7,
    }

    async with semaphore:
        try:
            resp = await client.get(url, params=params, timeout=5.0)
            if resp.status_code == 200:
                data = resp.json()
                hourly = data.get("hourly", {})
                times = hourly.get("time", [])

                if times:
                    # Match closest hour to ETA
                    target_hour_str = eta_dt.strftime("%Y-%m-%dT%H:00")
                    idx = -1
                    if target_hour_str in times:
                        idx = times.index(target_hour_str)
                    else:
                        # Find minimum time difference
                        for i, t_str in enumerate(times):
                            try:
                                t_dt = datetime.fromisoformat(t_str)
                                # naive comparison
                                diff_s = abs((eta_dt.replace(tzinfo=None) - t_dt.replace(tzinfo=None)).total_seconds())
                                if diff_s < 3600:
                                    idx = i
                                    break
                            except Exception:
                                continue

                    if idx >= 0:
                        wind_list = hourly.get("wind_speed_10m", [])
                        rain_list = hourly.get("rain", []) or hourly.get("precipitation", [])
                        snow_list = hourly.get("snowfall", [])

                        wind_mph = float(wind_list[idx]) if idx < len(wind_list) and wind_list[idx] is not None else 0.0
                        rain_in_hr = float(rain_list[idx]) if idx < len(rain_list) and rain_list[idx] is not None else 0.0
                        snow_in_hr = float(snow_list[idx]) if idx < len(snow_list) and snow_list[idx] is not None else 0.0

                        return {
                            "wind_mph": round(wind_mph, 1),
                            "rain_in_hr": round(rain_in_hr, 2),
                            "snow_in_hr": round(snow_in_hr, 2),
                            "forecast_timestamp": times[idx],
                            "source": "open-meteo",
                            "quality": "FORECAST",
                        }
                    else:
                        # Beyond forecast horizon
                        return {
                            "wind_mph": None,
                            "rain_in_hr": None,
                            "snow_in_hr": None,
                            "forecast_timestamp": None,
                            "source": "open-meteo",
                            "quality": "OUT_OF_HORIZON",
                            "warning": "ETA is beyond the 7-day weather forecast horizon",
                        }

        except Exception as e:
            logger.debug("Open-Meteo call error: %s, using fallback", e)

    # Fallback to simulated forecast
    return _simulated_weather_fallback(latitude, longitude, eta_dt)


async def enrich_checkpoints_with_weather(
    checkpoints: List[Dict[str, Any]],
    client: Optional[httpx.AsyncClient] = None,
) -> List[Dict[str, Any]]:
    """
    Enrich all checkpoints with forecast weather at their respective ETAs in parallel.
    Uses coordinate-hour caching to avoid duplicate queries.
    """
    if not checkpoints:
        return []

    owns_client = False
    if client is None:
        client = httpx.AsyncClient(timeout=8.0)
        owns_client = True

    semaphore = asyncio.Semaphore(10)
    cache: Dict[str, Dict[str, Any]] = {}

    try:
        tasks = []
        for cp in checkpoints:
            lat = cp["latitude"]
            lon = cp["longitude"]
            eta = cp["eta"]
            # Cache key rounded to ~7 miles and 1-hour resolution
            hour_prefix = eta[:13] if len(eta) >= 13 else eta
            cache_key = f"{round(lat, 1)}:{round(lon, 1)}:{hour_prefix}"

            async def _fetch_and_attach(checkpoint=cp, c_key=cache_key):
                if c_key in cache:
                    checkpoint["weather"] = cache[c_key]
                else:
                    wx = await fetch_checkpoint_weather(
                        checkpoint["latitude"],
                        checkpoint["longitude"],
                        checkpoint["eta"],
                        client,
                        semaphore,
                    )
                    cache[c_key] = wx
                    checkpoint["weather"] = wx

            tasks.append(_fetch_and_attach())

        await asyncio.gather(*tasks)
        return checkpoints

    finally:
        if owns_client:
            await client.aclose()

