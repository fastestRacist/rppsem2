"""Детерминированная генерация тестовых рейсов для собственной БД и поставщиков."""
from __future__ import annotations

import random
from datetime import date, datetime, time, timedelta
from typing import Iterator

AIRPORTS = tuple(f"A{i:02d}" for i in range(30))
BASE_DATE = date(2026, 1, 1)
DAYS = 120
OWN_FLIGHTS_PER_DAY = 1500
PROVIDER_FLIGHTS_PER_DAY = 500


def generate_flights(carrier: str, flight_date: date, count: int, seed_key: str) -> list[dict]:
    """Для одинаковых carrier/date/seed_key всегда возвращает одинаковые рейсы."""
    rng = random.Random(f"{seed_key}:{carrier}:{flight_date.isoformat()}")
    result = []
    start = datetime.combine(flight_date, time.min)
    for index in range(count):
        origin = rng.choice(AIRPORTS)
        destination = rng.choice(AIRPORTS)
        while destination == origin:
            destination = rng.choice(AIRPORTS)
        departure = start + timedelta(minutes=rng.randrange(0, 22 * 60 + 1))
        duration = timedelta(minutes=rng.randrange(60, 361))
        arrival = departure + duration
        result.append({
            "carrier": carrier,
            "flight_no": f"{carrier}-{flight_date:%Y%m%d}-{index + 1:04d}",
            "origin": origin,
            "destination": destination,
            "departure_at": departure,
            "arrival_at": arrival,
            "price": rng.randrange(3500, 25001),
        })
    return result


def generate_own_period() -> Iterator[dict]:
    for day_offset in range(DAYS):
        flight_date = BASE_DATE + timedelta(days=day_offset)
        yield from generate_flights("OWN", flight_date, OWN_FLIGHTS_PER_DAY, "own-schedule-v1")


def flights_to_json(flights: list[dict]) -> list[dict]:
    return [
        {
            **flight,
            "departure_at": flight["departure_at"].isoformat(),
            "arrival_at": flight["arrival_at"].isoformat(),
        }
        for flight in flights
    ]
