"""Общая заглушка авиапоставщика. Параметры задаются переменными окружения."""
from __future__ import annotations

import asyncio
import os
import random
from datetime import date

from fastapi import FastAPI, HTTPException, Query

from flight_data import PROVIDER_FLIGHTS_PER_DAY, flights_to_json, generate_flights

PROVIDER_NAME = os.getenv("PROVIDER_NAME", "provider1")
AVG_DELAY_MS = float(os.getenv("AVG_DELAY_MS", "300"))
JITTER_FRACTION = float(os.getenv("JITTER_FRACTION", "0.30"))
ERROR_RATE = float(os.getenv("ERROR_RATE", "0.05"))
SLOW_RATE = float(os.getenv("SLOW_RATE", "0"))
SLOW_DELAY_MS = float(os.getenv("SLOW_DELAY_MS", "3000"))
FLIGHTS_PER_DAY = int(os.getenv("FLIGHTS_PER_DAY", str(PROVIDER_FLIGHTS_PER_DAY)))

app = FastAPI()


@app.get("/flights")
async def get_flights(flight_date: date = Query(alias="date")):
    if random.random() < SLOW_RATE:
        delay_ms = SLOW_DELAY_MS
    else:
        delay_ms = random.uniform(
            AVG_DELAY_MS * (1 - JITTER_FRACTION),
            AVG_DELAY_MS * (1 + JITTER_FRACTION),
        )
    await asyncio.sleep(delay_ms / 1000)

    if random.random() < ERROR_RATE:
        raise HTTPException(status_code=500, detail="Ошибка поставщика")

    flights = generate_flights(PROVIDER_NAME.upper(), flight_date, FLIGHTS_PER_DAY, "provider-schedule-v1")
    return {"provider": PROVIDER_NAME, "flights": flights_to_json(flights)}


@app.get("/health")
async def health():
    return {"status": "ok", "provider": PROVIDER_NAME}
