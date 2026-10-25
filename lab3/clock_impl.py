"""Прикладные часы со сдвигом. Реализация порта Clock."""
from datetime import datetime, timedelta

from library import Clock, DomainError


class ClockShiftBackward(DomainError):
    """Попытка перевести часы приложения назад."""


class AppClock:
    def __init__(self):
        self._offset = timedelta(0)

    def now(self) -> datetime:
        return datetime.now() + self._offset

    def shift_to(self, new_now: datetime) -> None:
        current = self.now()
        if new_now < current:
            raise ClockShiftBackward(
                f"Нельзя перевести часы назад: текущее {current.isoformat()}, "
                f"запрошено {new_now.isoformat()}"
            )
        self._offset = new_now - datetime.now()