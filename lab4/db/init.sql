CREATE TABLE IF NOT EXISTS flights (
    id BIGSERIAL PRIMARY KEY,
    carrier VARCHAR(32) NOT NULL,
    flight_no VARCHAR(64) NOT NULL,
    origin VARCHAR(8) NOT NULL,
    destination VARCHAR(8) NOT NULL,
    departure_at TIMESTAMP NOT NULL,
    arrival_at TIMESTAMP NOT NULL,
    price INTEGER NOT NULL CHECK (price > 0),
    UNIQUE (carrier, flight_no)
);

CREATE INDEX IF NOT EXISTS idx_flights_departure_at ON flights (departure_at);
