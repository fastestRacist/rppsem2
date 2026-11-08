"""Версия 4.2: параллельный асинхронный опрос поставщиков и PostgreSQL."""
from __future__ import annotations

import asyncio
import os
import time
from contextlib import asynccontextmanager
from datetime import date as date_type, datetime, time as day_time, timedelta

import httpx
from fastapi import FastAPI, HTTPException, Query, Request
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from route_builder import build_routes
PROVIDERS = (
    ("provider1", os.getenv("PROVIDER1_URL", "http://provider1:8000")),
    ("provider2", os.getenv("PROVIDER2_URL", "http://provider2:8000")),
    ("provider3", os.getenv("PROVIDER3_URL", "http://provider3:8000")),
)
RETRY_DELAY_SECONDS = 0.2


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.http_client = httpx.AsyncClient()
    database_url = os.getenv(
        "ASYNC_DATABASE_URL",
        "postgresql+asyncpg://postgres:postgres@db:5432/flights",
    )
    app.state.db_engine = create_async_engine(database_url, pool_size=20, max_overflow=20, pool_pre_ping=True)
    yield
    await app.state.http_client.aclose()
    await app.state.db_engine.dispose()


app = FastAPI(lifespan=lifespan)


async def load_own_flights_async(engine, flight_date: date_type) -> list[dict]:
    start = datetime.combine(flight_date, day_time.min)
    end = start + timedelta(days=1)
    query = text("""
        SELECT carrier, flight_no, origin, destination, departure_at, arrival_at, price
        FROM flights
        WHERE departure_at >= :start AND departure_at < :end
    """)
    async with engine.connect() as connection:
        result = await connection.execute(query, {"start": start, "end": end})
        return [dict(row) for row in result.mappings().all()]


async def fetch_provider_async(client: httpx.AsyncClient, name: str, base_url: str, flight_date: date_type):
    """Общий timeout=2 с учётом паузы и единственного повтора."""
    try:
        async with asyncio.timeout(2.0):
            for attempt in range(2):
                try:
                    response = await client.get(
                        f"{base_url}/flights",
                        params={"date": flight_date.isoformat()},
                    )
                    response.raise_for_status()
                    return response.json()["flights"]
                except (httpx.HTTPError, ValueError, KeyError, TypeError):
                    if attempt == 1:
                        return None
                    await asyncio.sleep(RETRY_DELAY_SECONDS)
    except TimeoutError:
        return None
    return None


@app.get("/search")
async def search(
    request: Request,
    origin: str = Query(min_length=1),
    destination: str = Query(min_length=1),
    flight_date: date_type = Query(alias="date"),
):
    started = time.perf_counter()
    client = request.app.state.http_client
    engine = request.app.state.db_engine

    results = await asyncio.gather(
        load_own_flights_async(engine, flight_date),
        *(
            fetch_provider_async(client, name, url, flight_date)
            for name, url in PROVIDERS
        ),
        return_exceptions=True,
    )

    own_result = results[0]
    if isinstance(own_result, Exception):
        raise HTTPException(status_code=503, detail="Не удалось прочитать расписание")

    own_flights = own_result
    all_flights = list(own_flights)
    not_responded = []
    for (name, _), provider_result in zip(PROVIDERS, results[1:]):
        if isinstance(provider_result, Exception) or provider_result is None:
            not_responded.append(name)
        else:
            all_flights.extend(provider_result)

    if len(not_responded) == len(PROVIDERS) and not own_flights:
        raise HTTPException(
            status_code=503,
            detail={
                "message": "Поиск временно недоступен",
                "routes": [],
                "not_responded_providers": not_responded,
                "processing_time_ms": round((time.perf_counter() - started) * 1000, 2),
            },
        )

    routes = build_routes(all_flights, origin, destination, flight_date, limit=20)
    return {
        "routes": routes,
        "not_responded_providers": not_responded,
        "processing_time_ms": round((time.perf_counter() - started) * 1000, 2),
    }


@app.get("/health")
async def health():
    return {"status": "ok"}
