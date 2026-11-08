"""Загрузка 120 дней расписания (1500 рейсов в сутки) в PostgreSQL."""
import os
from sqlalchemy import Column, DateTime, Integer, BigInteger, MetaData, String, Table, create_engine, insert, text

from flight_data import generate_own_period

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+psycopg://postgres:postgres@localhost:5432/flights")
metadata = MetaData()
flights_table = Table(
    "flights", metadata,
    Column("id", BigInteger, primary_key=True),
    Column("carrier", String(32)),
    Column("flight_no", String(64)),
    Column("origin", String(8)),
    Column("destination", String(8)),
    Column("departure_at", DateTime),
    Column("arrival_at", DateTime),
    Column("price", Integer),
)


def main():
    engine = create_engine(DATABASE_URL)
    rows = list(generate_own_period())
    with engine.begin() as connection:
        connection.execute(text("TRUNCATE TABLE flights RESTART IDENTITY"))
        for start in range(0, len(rows), 5000):
            connection.execute(insert(flights_table), rows[start:start + 5000])
    engine.dispose()
    print(f"Загружено рейсов: {len(rows)}")


if __name__ == "__main__":
    main()
