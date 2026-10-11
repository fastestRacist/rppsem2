from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum
from math import ceil
from typing import Protocol


class DomainError(Exception):
    pass


class DomainInvariantViolation(DomainError):
    pass


class InvalidValueObject(DomainError):
    pass


class AggregateNotFound(DomainError):
    pass


def _non_empty(value: str, name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise InvalidValueObject(f"{name} не может быть пустым")


def _money(value, name: str) -> Decimal:
    try:
        result = Decimal(str(value))
    except Exception as exc:
        raise InvalidValueObject(f"Некорректное значение: {name}") from exc
    if not result.is_finite() or result < 0:
        raise InvalidValueObject(f"{name} не может быть отрицательным")
    return result


# Объекты-значения
@dataclass(frozen=True)
class ScooterId:
    value: str
    def __post_init__(self): _non_empty(self.value, "ID самоката")


@dataclass(frozen=True)
class UserId:
    value: str
    def __post_init__(self): _non_empty(self.value, "ID пользователя")


@dataclass(frozen=True)
class RideId:
    value: str
    def __post_init__(self): _non_empty(self.value, "ID поездки")


@dataclass(frozen=True)
class BatteryLevel:
    percent: int
    def __post_init__(self):
        if type(self.percent) is not int or not 0 <= self.percent <= 100:
            raise InvalidValueObject("Заряд должен быть от 0 до 100")


@dataclass(frozen=True)
class Tariff:
    price_per_minute: Decimal
    minimum_price: Decimal
    def __post_init__(self):
        object.__setattr__(self, "price_per_minute", _money(self.price_per_minute, "Цена за минуту"))
        object.__setattr__(self, "minimum_price", _money(self.minimum_price, "Минимальная стоимость"))


@dataclass(frozen=True)
class RideCost:
    amount: Decimal
    def __post_init__(self):
        object.__setattr__(self, "amount", _money(self.amount, "Стоимость поездки"))


class ScooterStatus(str, Enum):
    AVAILABLE = "available"
    RENTED = "rented"
    MAINTENANCE = "maintenance"


# Агрегат 1: Scooter — корень, защищающий статус и заряд самоката.
class Scooter:
    def __init__(self, scooter_id: ScooterId, battery: BatteryLevel,
                 status: ScooterStatus = ScooterStatus.AVAILABLE):
        if not isinstance(scooter_id, ScooterId) or not isinstance(battery, BatteryLevel):
            raise DomainInvariantViolation("Некорректные данные самоката")
        if not isinstance(status, ScooterStatus):
            raise DomainInvariantViolation("Некорректный статус самоката")
        self._id = scooter_id
        self._battery = battery
        self._status = status

    @property
    def id(self): return self._id
    @property
    def battery(self): return self._battery
    @property
    def status(self): return self._status

    def rent(self, minimum_battery: BatteryLevel):
        if self._status is not ScooterStatus.AVAILABLE:
            raise DomainInvariantViolation("Самокат не свободен")
        if not isinstance(minimum_battery, BatteryLevel):
            raise DomainInvariantViolation("Неверный минимальный заряд")
        if self._battery.percent < minimum_battery.percent:
            raise DomainInvariantViolation("Заряда недостаточно для аренды")
        self._status = ScooterStatus.RENTED

    def finish_rental(self):
        if self._status is not ScooterStatus.RENTED:
            raise DomainInvariantViolation("Самокат не арендован")
        self._status = ScooterStatus.AVAILABLE

    def to_state(self):
        return {"id": self.id.value, "battery": self.battery.percent,
                "status": self.status.value}


# Агрегат 2: Ride — отдельная поездка
class Ride:
    def __init__(self, ride_id: RideId, scooter_id: ScooterId, user_id: UserId,
                 started_at: datetime, tariff: Tariff,
                 finished_at: datetime | None = None, cost: RideCost | None = None):
        if not all(isinstance(x, t) for x, t in (
            (ride_id, RideId), (scooter_id, ScooterId), (user_id, UserId), (tariff, Tariff)
        )):
            raise DomainInvariantViolation("Некорректные данные поездки")
        if not isinstance(started_at, datetime):
            raise DomainInvariantViolation("Время начала должно быть datetime")
        if finished_at is None:
            if cost is not None:
                raise DomainInvariantViolation("У незавершённой поездки не может быть цены")
        else:
            if not isinstance(finished_at, datetime) or finished_at < started_at:
                raise DomainInvariantViolation("Окончание поездки раньше начала")
            if not isinstance(cost, RideCost):
                raise DomainInvariantViolation("У завершённой поездки должна быть стоимость")
            minutes = ceil((finished_at - started_at).total_seconds() / 60)
            expected_cost = max(tariff.minimum_price, tariff.price_per_minute * minutes)
            if cost.amount != expected_cost:
                raise DomainInvariantViolation("Стоимость поездки не соответствует тарифу")
        self._id = ride_id
        self._scooter_id = scooter_id
        self._user_id = user_id
        self._started_at = started_at
        self._tariff = tariff
        self._finished_at = finished_at
        self._cost = cost

    @property
    def id(self): return self._id
    @property
    def scooter_id(self): return self._scooter_id
    @property
    def user_id(self): return self._user_id
    @property
    def is_active(self): return self._finished_at is None
    @property
    def cost(self): return self._cost

    def finish(self, finished_at: datetime) -> RideCost:
        if not self.is_active:
            raise DomainInvariantViolation("Поездка уже завершена")
        if not isinstance(finished_at, datetime) or finished_at < self._started_at:
            raise DomainInvariantViolation("Окончание поездки раньше начала")
        minutes = ceil((finished_at - self._started_at).total_seconds() / 60)
        amount = max(self._tariff.minimum_price, self._tariff.price_per_minute * minutes)
        self._finished_at = finished_at
        self._cost = RideCost(amount)
        return self._cost

    def to_state(self):
        return {"id": self.id.value, "scooter_id": self.scooter_id.value,
                "user_id": self.user_id.value, "started_at": self._started_at,
                "price_per_minute": str(self._tariff.price_per_minute),
                "minimum_price": str(self._tariff.minimum_price),
                "finished_at": self._finished_at,
                "cost": str(self._cost.amount) if self._cost else None}


# Фабрики восстановления повторно проверяют инварианты через конструкторы.
class ScooterFactory:
    @staticmethod
    def restore(state: dict) -> Scooter:
        try:
            status = ScooterStatus(state["status"])
        except (ValueError, KeyError) as exc:
            raise DomainInvariantViolation("Некорректный статус самоката") from exc
        return Scooter(ScooterId(state["id"]), BatteryLevel(state["battery"]), status)


class RideFactory:
    @staticmethod
    def restore(state: dict) -> Ride:
        cost = RideCost(state["cost"]) if state["cost"] is not None else None
        tariff = Tariff(state["price_per_minute"], state["minimum_price"])
        return Ride(RideId(state["id"]), ScooterId(state["scooter_id"]),
                    UserId(state["user_id"]), state["started_at"], tariff,
                    state["finished_at"], cost)


class ScooterRepository(Protocol):
    def get(self, scooter_id: ScooterId) -> Scooter: ...
    def save(self, scooter: Scooter) -> None: ...


class RideRepository(Protocol):
    def get(self, ride_id: RideId) -> Ride: ...
    def save(self, ride: Ride) -> None: ...


class InMemoryScooterRepository:
    def __init__(self): self._data = {}

    def get(self, scooter_id: ScooterId) -> Scooter:
        if scooter_id.value not in self._data:
            raise AggregateNotFound("Самокат не найден")
        return ScooterFactory.restore(self._data[scooter_id.value])

    def save(self, scooter: Scooter) -> None:
        self._data[scooter.id.value] = scooter.to_state()


class InMemoryRideRepository:
    def __init__(self): self._data = {}

    def get(self, ride_id: RideId) -> Ride:
        if ride_id.value not in self._data:
            raise AggregateNotFound("Поездка не найдена")
        return RideFactory.restore(self._data[ride_id.value])

    def save(self, ride: Ride) -> None:
        self._data[ride.id.value] = ride.to_state()


# Доменный сервис меняет два агрегата при начале и завершении поездки.
class ScooterRentalService:
    def __init__(self, scooters: ScooterRepository, rides: RideRepository):
        self._scooters = scooters
        self._rides = rides

    def start_ride(self, scooter_id: ScooterId, user_id: UserId, ride_id: RideId,
                   started_at: datetime, tariff: Tariff,
                   minimum_battery: BatteryLevel) -> Ride:
        scooter = self._scooters.get(scooter_id)
        ride = Ride(ride_id, scooter_id, user_id, started_at, tariff)
        scooter.rent(minimum_battery)
        self._scooters.save(scooter)
        self._rides.save(ride)
        return ride

    def finish_ride(self, ride_id: RideId, finished_at: datetime) -> RideCost:
        ride = self._rides.get(ride_id)
        scooter = self._scooters.get(ride.scooter_id)
        cost = ride.finish(finished_at)
        scooter.finish_rental()
        self._rides.save(ride)
        self._scooters.save(scooter)
        return cost
