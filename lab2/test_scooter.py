import unittest
from datetime import datetime, timedelta
from decimal import Decimal

from scooter import (
    Scooter, ScooterId, UserId, RideId, BatteryLevel, Tariff, RideCost,
    ScooterStatus, DomainInvariantViolation, InvalidValueObject,
    ScooterFactory, InMemoryScooterRepository, InMemoryRideRepository,
    ScooterRentalService,
)


class ScooterTests(unittest.TestCase):
    def setUp(self):
        self.scooters = InMemoryScooterRepository()
        self.rides = InMemoryRideRepository()
        self.service = ScooterRentalService(self.scooters, self.rides)
        self.scooter_id = ScooterId("scooter-1")
        self.user_id = UserId("user-1")
        self.ride_id = RideId("ride-1")
        self.start = datetime(2026, 10, 1, 10, 0)
        self.tariff = Tariff(Decimal("2"), Decimal("5"))
        self.scooters.save(Scooter(self.scooter_id, BatteryLevel(80)))

    def test_low_battery_blocks_rent(self):
        self.scooters.save(Scooter(self.scooter_id, BatteryLevel(10)))
        with self.assertRaises(DomainInvariantViolation):
            self.service.start_ride(self.scooter_id, self.user_id, self.ride_id,
                                    self.start, self.tariff, BatteryLevel(20))

    def test_ride_cost_and_scooter_status(self):
        self.service.start_ride(self.scooter_id, self.user_id, self.ride_id,
                                self.start, self.tariff, BatteryLevel(20))
        cost = self.service.finish_ride(self.ride_id, self.start + timedelta(minutes=3))
        self.assertEqual(cost, RideCost(Decimal("6")))
        self.assertEqual(self.scooters.get(self.scooter_id).status, ScooterStatus.AVAILABLE)

    def test_ride_cannot_finish_before_start_or_twice(self):
        self.service.start_ride(self.scooter_id, self.user_id, self.ride_id,
                                self.start, self.tariff, BatteryLevel(20))
        with self.assertRaises(DomainInvariantViolation):
            self.service.finish_ride(self.ride_id, self.start - timedelta(seconds=1))
        self.service.finish_ride(self.ride_id, self.start + timedelta(minutes=1))
        with self.assertRaises(DomainInvariantViolation):
            self.service.finish_ride(self.ride_id, self.start + timedelta(minutes=2))

    def test_value_object_and_restore_validate(self):
        with self.assertRaises(InvalidValueObject):
            BatteryLevel(101)
        with self.assertRaises(DomainInvariantViolation):
            ScooterFactory.restore({"id": "s", "battery": 50, "status": "unknown"})


if __name__ == "__main__":
    unittest.main()
