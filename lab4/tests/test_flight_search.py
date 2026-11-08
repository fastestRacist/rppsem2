import unittest
from datetime import date, datetime, timedelta

from flight_data import generate_flights, generate_own_period, OWN_FLIGHTS_PER_DAY, DAYS
from route_builder import build_routes
from service_async_io import build_routes as build_routes_in_app

DAY = date(2026, 1, 1)


def flight(number, origin, destination, dep, duration_hours, price):
    departure = datetime.fromisoformat(dep)
    return {
        "carrier": "TEST",
        "flight_no": number,
        "origin": origin,
        "destination": destination,
        "departure_at": departure,
        "arrival_at": departure + timedelta(hours=duration_hours),
        "price": price,
    }


class FlightSearchTests(unittest.TestCase):
    def test_provider_generation_is_deterministic(self):
        a = generate_flights("P1", DAY, 500, "test")
        b = generate_flights("P1", DAY, 500, "test")
        self.assertEqual(a, b)

    def test_own_schedule_has_120_days_and_1500_flights_per_day(self):
        generated = list(generate_own_period())
        self.assertEqual(len(generated), DAYS * OWN_FLIGHTS_PER_DAY)
        self.assertEqual(generated[0], next(generate_own_period()))

    def test_direct_route(self):
        flights = [flight("F1", "A00", "A01", "2026-01-01T08:00:00", 2, 1000)]
        routes = build_routes(flights, "A00", "A01", DAY)
        self.assertEqual(len(routes), 1)
        self.assertEqual(routes[0]["total_price"], 1000)
        self.assertEqual(routes[0]["transfers"], 0)

    def test_one_transfer_with_layover_between_one_and_six_hours(self):
        flights = [
            flight("F1", "A00", "A01", "2026-01-01T08:00:00", 2, 1000),
            flight("F2", "A01", "A02", "2026-01-01T11:00:00", 1, 1200),
        ]
        routes = build_routes(flights, "A00", "A02", DAY)
        self.assertEqual(len(routes), 1)
        self.assertEqual(routes[0]["transfers"], 1)
        self.assertEqual(routes[0]["total_price"], 2200)

    def test_two_transfers_and_no_repeated_airports(self):
        flights = [
            flight("F1", "A00", "A01", "2026-01-01T06:00:00", 2, 1000),
            flight("F2", "A01", "A02", "2026-01-01T09:00:00", 2, 1100),
            flight("F3", "A02", "A03", "2026-01-01T13:00:00", 2, 1200),
            flight("BAD", "A02", "A00", "2026-01-01T13:00:00", 2, 10),
        ]
        routes = build_routes(flights, "A00", "A03", DAY)
        self.assertEqual(len(routes), 1)
        self.assertEqual(routes[0]["transfers"], 2)
        self.assertEqual(len(routes[0]["airports"]), len(set(routes[0]["airports"])))

    def test_rejects_short_layover_and_flights_on_other_date(self):
        flights = [
            flight("F1", "A00", "A01", "2026-01-01T08:00:00", 2, 1000),
            flight("SHORT", "A01", "A02", "2026-01-01T10:30:00", 1, 100),
            flight("OTHER", "A01", "A02", "2026-01-02T12:00:00", 1, 100),
        ]
        self.assertEqual(build_routes(flights, "A00", "A02", DAY), [])

    def test_routes_are_sorted_by_category_then_price(self):
        flights = [
            flight("DIRECT", "A00", "A03", "2026-01-01T08:00:00", 2, 9000),
            flight("FIRST", "A00", "A01", "2026-01-01T06:00:00", 1, 100),
            flight("SECOND", "A01", "A03", "2026-01-01T08:00:00", 1, 100),
            flight("LEG1", "A00", "A02", "2026-01-01T05:00:00", 1, 50),
            flight("LEG2", "A02", "A04", "2026-01-01T07:00:00", 1, 50),
            flight("LEG3", "A04", "A03", "2026-01-01T09:00:00", 1, 50),
        ]
        routes = build_routes(flights, "A00", "A03", DAY)
        self.assertEqual([route["category"] for route in routes], ["direct", "one_transfer", "two_transfers"])
        self.assertEqual([route["total_price"] for route in routes], [9000, 200, 150])

    def test_stage_three_app_contains_the_same_route_rules(self):
        flights = [
            flight("EXPENSIVE_DIRECT", "A00", "A02", "2026-01-01T08:00:00", 2, 9000),
            flight("LEG1", "A00", "A01", "2026-01-01T06:00:00", 1, 100),
            flight("LEG2", "A01", "A02", "2026-01-01T08:00:00", 1, 100),
        ]
        self.assertEqual(
            build_routes_in_app(flights, "A00", "A02", DAY),
            build_routes(flights, "A00", "A02", DAY),
        )

    def test_returns_no_more_than_twenty_routes(self):
        flights = []
        for i in range(25):
            flights.append(flight(f"F{i}", "A00", "A01", "2026-01-01T08:00:00", 2, 1000 + i))
        self.assertEqual(len(build_routes(flights, "A00", "A01", DAY)), 20)

    def test_repeated_airport_and_layover_over_six_hours_are_rejected(self):
        flights = [
            flight("F1", "A00", "A01", "2026-01-01T06:00:00", 2, 1000),
            flight("CYCLE", "A01", "A00", "2026-01-01T09:00:00", 1, 10),
            flight("F2", "A00", "A02", "2026-01-01T11:00:00", 1, 1000),
            flight("LONG", "A01", "A03", "2026-01-01T15:00:00", 1, 10),
        ]
        routes = build_routes(flights, "A00", "A03", DAY)
        self.assertEqual(routes, [])

    def test_does_not_build_more_than_two_transfers(self):
        flights = [
            flight("F1", "A00", "A01", "2026-01-01T05:00:00", 1, 100),
            flight("F2", "A01", "A02", "2026-01-01T07:00:00", 1, 100),
            flight("F3", "A02", "A03", "2026-01-01T09:00:00", 1, 100),
            flight("F4", "A03", "A04", "2026-01-01T11:00:00", 1, 100),
        ]
        self.assertEqual(build_routes(flights, "A00", "A04", DAY), [])


if __name__ == "__main__":
    unittest.main()
