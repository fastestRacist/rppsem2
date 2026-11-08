"""Версия 4.1: изменены только обработчики на async def; внутри остался блокирующий код."""
from datetime import date as date_type

from fastapi import FastAPI, HTTPException, Query

from service_common import SearchUnavailable, search_sync

app = FastAPI()


@app.get("/search")
async def search(
    origin: str = Query(min_length=1),
    destination: str = Query(min_length=1),
    flight_date: date_type = Query(alias="date"),
):
    try:
        return search_sync(origin, destination, flight_date)
    except SearchUnavailable as error:
        raise HTTPException(
            status_code=503,
            detail={
                "message": str(error),
                "routes": [],
                "not_responded_providers": error.not_responded,
                "processing_time_ms": error.processing_time_ms,
            },
        )


@app.get("/health")
async def health():
    return {"status": "ok"}
