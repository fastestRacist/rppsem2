"""Построение маршрутов без обращений к сети и базе данных (этап 4)."""
from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime


def _as_datetime(value):
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(value)


def _normalise(flight: dict) -> dict:
    item = dict(flight)
    item["departure_at"] = _as_datetime(item["departure_at"])
    item["arrival_at"] = _as_datetime(item["arrival_at"])
    item["price"] = int(item["price"])
    return item


def build_routes(
    flights: list[dict],
    origin: str,
    destination: str,
    flight_date: date,
    limit: int = 20,
) -> list[dict]:
    """Строит маршруты, сортирует по категории и цене, возвращает первые limit."""
    if origin == destination:
        return []

    adjacency = defaultdict(list)
    for raw in flights:
        flight = _normalise(raw)
        if flight["departure_at"].date() == flight_date:
            adjacency[flight["origin"]].append(flight)
    for outgoing in adjacency.values():
        outgoing.sort(key=lambda item: item["departure_at"])

    found = []

    def add_route(legs: list[dict]):
        transfers = len(legs) - 1
        category = ("direct", "one_transfer", "two_transfers")[transfers]
        total = sum(leg["price"] for leg in legs)
        found.append({
            "category": category,
            "flights": [
                {
                    **leg,
                    "departure_at": leg["departure_at"].isoformat(),
                    "arrival_at": leg["arrival_at"].isoformat(),
                }
                for leg in legs
            ],
            "airports": [legs[0]["origin"]] + [leg["destination"] for leg in legs],
            "total_price": total,
            "transfers": transfers,
        })

    one_hour = 3600
    six_hours = 6 * 3600

    for first in adjacency.get(origin, []):
        visited = {origin, first["destination"]}
        if first["destination"] == destination:
            add_route([first])
            continue

        for second in adjacency.get(first["destination"], []):
            if second["destination"] in visited:
                continue
            layover = (second["departure_at"] - first["arrival_at"]).total_seconds()
            if not one_hour <= layover <= six_hours:
                continue
            visited2 = visited | {second["destination"]}
            if second["destination"] == destination:
                add_route([first, second])
                continue

            for third in adjacency.get(second["destination"], []):
                if third["destination"] in visited2:
                    continue
                layover2 = (third["departure_at"] - second["arrival_at"]).total_seconds()
                if not one_hour <= layover2 <= six_hours:
                    continue
                if third["destination"] == destination:
                    add_route([first, second, third])

    # Категории: прямой рейс, одна пересадка, две пересадки.
    # Внутри категории маршруты упорядочиваются по стоимости.
    found.sort(key=lambda route: (route["transfers"], route["total_price"], route["airports"]))
    return found[:limit]
