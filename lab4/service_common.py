"""Общие функции синхронной версии: БД, последовательный опрос и ответ."""
from __future__ import annotations

import os
import time
from datetime import date, datetime, time as day_time, timedelta
from functools import lru_cache

import requests
from sqlalchemy import create_engine, text

from route_builder import build_routes

PROVIDERS = (
    ("provider1", os.getenv("PROVIDER1_URL", "http://provider1:8000")),
    ("provider2", os.getenv("PROVIDER2_URL", "http://provider2:8000")),
    ("provider3", os.getenv("PROVIDER3_URL", "http://provider3:8000")),
)
PROVIDER_TIMEOUT_SECONDS = 2.0
RETRY_DELAY_SECONDS = 0.2


class SearchUnavailable(Exception):
    def __init__(self, not_responded: list[str], processing_time_ms: float):
        self.not_responded = not_responded
        self.processing_time_ms = processing_time_ms
        super().__init__("Поиск временно недоступен")


@lru_cache(maxsize=1)
def get_sync_engine():
    url = os.getenv("DATABASE_URL", "postgresql+psycopg://postgres:postgres@db:5432/flights")
    return create_engine(url, pool_size=20, max_overflow=20, pool_pre_ping=True)


def load_own_flights_sync(flight_date: date) -> list[dict]:
    start = datetime.combine(flight_date, day_time.min)
    end = start + timedelta(days=1)
    query = text("""
        SELECT carrier, flight_no, origin, destination, departure_at, arrival_at, price
        FROM flights
        WHERE departure_at >= :start AND departure_at < :end
    """)
    with get_sync_engine().connect() as connection:
        rows = connection.execute(query, {"start": start, "end": end}).mappings().all()
    return [dict(row) for row in rows]


def fetch_provider_sync(name: str, base_url: str, flight_date: date) -> list[dict] | None:
    """Один общий двухсекундный срок на первый запрос, паузу и повтор."""
    deadline = time.monotonic() + PROVIDER_TIMEOUT_SECONDS
    for attempt in range(2):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return None
        try:
            response = requests.get(
                f"{base_url}/flights",
                params={"date": flight_date.isoformat()},
                timeout=remaining,
            )
            response.raise_for_status()
            if time.monotonic() > deadline:
                return None
            return response.json()["flights"]
        except (requests.RequestException, ValueError, KeyError, TypeError):
            if attempt == 1:
                return None
            remaining = deadline - time.monotonic()
            if remaining <= RETRY_DELAY_SECONDS:
                return None
            time.sleep(RETRY_DELAY_SECONDS)
    return None


def search_sync(origin: str, destination: str, flight_date: date) -> dict:
    started = time.perf_counter()
    own_flights = load_own_flights_sync(flight_date)
    all_flights = list(own_flights)
    not_responded = []

    for name, url in PROVIDERS:
        provider_flights = fetch_provider_sync(name, url, flight_date)
        if provider_flights is None:
            not_responded.append(name)
        else:
            all_flights.extend(provider_flights)

    if len(not_responded) == len(PROVIDERS) and not own_flights:
        elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
        raise SearchUnavailable(not_responded, elapsed_ms)

    routes = build_routes(all_flights, origin, destination, flight_date, limit=20)
    return {
        "routes": routes,
        "not_responded_providers": not_responded,
        "processing_time_ms": round((time.perf_counter() - started) * 1000, 2),
    }
