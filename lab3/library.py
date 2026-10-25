"""Доменная модель библиотеки — лабораторная №3.

Жизненный цикл выдачи реализован через паттерн State (GoF).
"""
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Protocol


# ─── Исключения ──────────────────────────────────────────────

class DomainError(Exception):
    pass


class DomainInvariantViolation(DomainError):
    pass


class InvalidValueObject(DomainError):
    pass


class AggregateNotFound(DomainError):
    pass


class TransitionNotAllowed(DomainError):
    def __init__(self, state_name: str, event_name: str):
        super().__init__(
            f"Событие '{event_name}' недопустимо в состоянии '{state_name}'"
        )
        self.state_name = state_name
        self.event_name = event_name


class GatewayUnresolved(DomainError):
    def __init__(self, gateway_name: str):
        super().__init__(f"Шлюз '{gateway_name}': ни одно условие не выполнено")
        self.gateway_name = gateway_name


# ─── Порт часов ──────────────────────────────────────────────

class Clock(Protocol):
    def now(self) -> datetime: ...


class SystemClock:
    def now(self) -> datetime:
        return datetime.now()


# ─── Вспомогательные функции ─────────────────────────────────

def _non_empty(value, name):
    if not isinstance(value, str) or not value.strip():
        raise InvalidValueObject(f"{name} не может быть пустым")


def _non_negative_money(value, name):
    try:
        result = Decimal(str(value))
    except Exception as exc:
        raise InvalidValueObject(f"Некорректное значение: {name}") from exc
    if not result.is_finite() or result < 0:
        raise InvalidValueObject(f"{name} не может быть отрицательным")
    return result


# ─── Объекты-значения ────────────────────────────────────────

class _ValueObject:
    __slots__ = ()

    def _key(self):
        return tuple(getattr(self, name) for name in self.__slots__)

    def __eq__(self, other):
        return type(self) is type(other) and self._key() == other._key()

    def __hash__(self):
        return hash((type(self).__name__, self._key()))

    def __repr__(self):
        parts = ", ".join(
            f"{n.lstrip('_')}={getattr(self, n)!r}" for n in self.__slots__
        )
        return f"{type(self).__name__}({parts})"


class BookId(_ValueObject):
    __slots__ = ("_value",)
    def __init__(self, value):
        _non_empty(value, "ID книги")
        self._value = value
    @property
    def value(self): return self._value


class ReaderId(_ValueObject):
    __slots__ = ("_value",)
    def __init__(self, value):
        _non_empty(value, "ID читателя")
        self._value = value
    @property
    def value(self): return self._value


class LoanId(_ValueObject):
    __slots__ = ("_value",)
    def __init__(self, value):
        _non_empty(value, "ID выдачи")
        self._value = value
    @property
    def value(self): return self._value


class LoanPeriod(_ValueObject):
    __slots__ = ("_issued_on", "_due_on")
    def __init__(self, issued_on, due_on):
        if type(issued_on) is not date or type(due_on) is not date:
            raise InvalidValueObject("Даты должны иметь тип date")
        if due_on < issued_on:
            raise InvalidValueObject("Срок возврата раньше даты выдачи")
        self._issued_on = issued_on
        self._due_on = due_on
    @property
    def issued_on(self): return self._issued_on
    @property
    def due_on(self): return self._due_on


class Fine(_ValueObject):
    __slots__ = ("_amount",)
    def __init__(self, amount):
        self._amount = _non_negative_money(amount, "Штраф")
    @property
    def amount(self): return self._amount


class FineRate(_ValueObject):
    __slots__ = ("_amount_per_day",)
    def __init__(self, amount_per_day):
        self._amount_per_day = _non_negative_money(amount_per_day, "Ставка штрафа")
    @property
    def amount_per_day(self): return self._amount_per_day


# ─── Доменные события ────────────────────────────────────────

@dataclass(frozen=True)
class LoanIssued:
    loan_id: LoanId
    at: datetime


@dataclass(frozen=True)
class CheckoutDenied:
    loan_id: LoanId
    reason: str
    at: datetime


@dataclass(frozen=True)
class ReservationExpired:
    loan_id: LoanId
    has_queue: bool
    at: datetime


@dataclass(frozen=True)
class LoanExtended:
    loan_id: LoanId
    new_due_on: date
    at: datetime


@dataclass(frozen=True)
class ExtensionDenied:
    loan_id: LoanId
    at: datetime


@dataclass(frozen=True)
class ReminderSent:
    loan_id: LoanId
    at: datetime


@dataclass(frozen=True)
class BookReturned:
    loan_id: LoanId
    returned_on: date
    fine: Fine | None
    at: datetime


@dataclass(frozen=True)
class DamageFineAdded:
    loan_id: LoanId
    amount: Fine
    at: datetime


@dataclass(frozen=True)
class DueDateExpired:
    loan_id: LoanId
    at: datetime


@dataclass(frozen=True)
class EscalatedToAdmin:
    loan_id: LoanId
    at: datetime


# ─── Состояния (паттерн State) ───────────────────────────────

class LoanState:
    """Базовый класс состояния — все события запрещены."""

    name = ""
    allowed = frozenset()
    is_final = False

    def pickup(self, loan, now):
        raise TransitionNotAllowed(self.name, "pickup")

    def deny_debt(self, loan, now):
        raise TransitionNotAllowed(self.name, "deny_debt")

    def expire_reservation(self, loan, has_queue, now):
        raise TransitionNotAllowed(self.name, "expire_reservation")

    def extend(self, loan, new_due_on, now):
        raise TransitionNotAllowed(self.name, "extend")

    def extend_denied(self, loan, now):
        raise TransitionNotAllowed(self.name, "extend_denied")

    def return_book(self, loan, returned_on, rate, now):
        raise TransitionNotAllowed(self.name, "return_book")

    def expire_due(self, loan, now):
        raise TransitionNotAllowed(self.name, "expire_due")

    def escalate_30(self, loan, now):
        raise TransitionNotAllowed(self.name, "escalate_30")


class Registered(LoanState):
    name = "Забронирована"
    allowed = frozenset({"pickup", "deny_debt", "expire_reservation"})

    def pickup(self, loan, now):
        return Issued()

    def deny_debt(self, loan, now):
        # self-loop: остаётся в «Забронирована», пока читатель не погасит долг
        return self

    def expire_reservation(self, loan, has_queue, now):
        return Transferred() if has_queue else Cancelled()


class Issued(LoanState):
    name = "Выдана"
    allowed = frozenset({"extend", "extend_denied", "return_book", "expire_due"})

    def extend(self, loan, new_due_on, now):
        if new_due_on <= loan.period.due_on:
            raise DomainInvariantViolation("Новый срок должен быть позже текущего")
        loan._update_due_on(new_due_on)
        return Extended()

    def extend_denied(self, loan, now):
        # self-loop: продление запрещено, книга остаётся на руках до старого срока
        return self

    def return_book(self, loan, returned_on, rate, now):
        _complete_return(loan, returned_on, rate)
        return Returned()

    def expire_due(self, loan, now):
        return Overdue()


class Extended(LoanState):
    name = "Продлена"
    allowed = frozenset({"return_book", "expire_due"})

    def return_book(self, loan, returned_on, rate, now):
        _complete_return(loan, returned_on, rate)
        return Returned()

    def expire_due(self, loan, now):
        return Overdue()


class Overdue(LoanState):
    name = "Просрочена"
    allowed = frozenset({"return_book", "escalate_30"})

    def return_book(self, loan, returned_on, rate, now):
        _complete_return(loan, returned_on, rate)
        return Returned()

    def escalate_30(self, loan, now):
        return Escalated()


class Returned(LoanState):
    name = "Возвращена"
    is_final = True


class Cancelled(LoanState):
    name = "Снята"
    is_final = True


class Transferred(LoanState):
    name = "Перенесена"
    is_final = True


class Escalated(LoanState):
    name = "Передана администрации"
    is_final = True


_STATE_FACTORY = {
    "Registered": Registered, "Issued": Issued,
    "Extended": Extended, "Overdue": Overdue,
    "Returned": Returned, "Cancelled": Cancelled,
    "Transferred": Transferred, "Escalated": Escalated,
}


def _complete_return(loan, returned_on, rate):
    if type(returned_on) is not date:
        raise DomainInvariantViolation("Дата возврата должна быть date")
    if returned_on < loan.period.issued_on:
        raise DomainInvariantViolation("Возврат раньше даты выдачи")
    late_days = max(0, (returned_on - loan.period.due_on).days)
    loan._set_return(returned_on, Fine(rate.amount_per_day * late_days))


# ─── Агрегат Loan ────────────────────────────────────────────

class Loan:
    """Агрегат «Выдача». Состояние хранится в приватном `_state`."""

    def __init__(self, loan_id, book_id, reader_id, period):
        if not all(isinstance(x, t) for x, t in (
            (loan_id, LoanId), (book_id, BookId),
            (reader_id, ReaderId), (period, LoanPeriod)
        )):
            raise DomainInvariantViolation("Некорректные данные выдачи")
        self._id = loan_id
        self._book_id = book_id
        self._reader_id = reader_id
        self._period = period
        self._state: LoanState = Registered()
        self._returned_on: date | None = None
        self._fine: Fine | None = None
        self._events: list = []

    # ─── Свойства (только чтение) ───
    @property
    def id(self): return self._id
    @property
    def book_id(self): return self._book_id
    @property
    def reader_id(self): return self._reader_id
    @property
    def period(self): return self._period
    @property
    def status(self): return self._state.name
    @property
    def allowed_events(self): return self._state.allowed
    @property
    def is_final(self): return self._state.is_final
    @property
    def fine(self): return self._fine
    @property
    def returned_on(self): return self._returned_on
    @property
    def events(self): return tuple(self._events)

    # ─── Методы событий (делегируются состоянию) ───
    def pickup(self, now):
        self._state = self._state.pickup(self, now)
        self._events.append(LoanIssued(self._id, now))

    def deny_debt(self, now):
        self._state = self._state.deny_debt(self, now)
        self._events.append(CheckoutDenied(self._id, "задолженность", now))

    def expire_reservation(self, has_queue, now):
        self._state = self._state.expire_reservation(self, has_queue, now)
        self._events.append(ReservationExpired(self._id, has_queue, now))

    def extend(self, new_due_on, now):
        self._state = self._state.extend(self, new_due_on, now)
        self._events.append(LoanExtended(self._id, new_due_on, now))

    def extend_denied(self, now):
        self._state = self._state.extend_denied(self, now)
        self._events.append(ExtensionDenied(self._id, now))

    def return_book(self, returned_on, rate, now):
        self._state = self._state.return_book(self, returned_on, rate, now)
        self._events.append(BookReturned(self._id, returned_on, self._fine, now))

    def expire_due(self, now):
        self._state = self._state.expire_due(self, now)
        self._events.append(DueDateExpired(self._id, now))

    def escalate_30(self, now):
        self._state = self._state.escalate_30(self, now)
        self._events.append(EscalatedToAdmin(self._id, now))

    # ─── Прочие доменные методы ───
    def check_overdue(self, returned_on):
        return returned_on > self._period.due_on

    def add_damage_fine(self, damage_fine, now):
        if not isinstance(damage_fine, Fine):
            raise DomainInvariantViolation("Штраф за повреждение должен быть Fine")
        self._fine = (Fine(self._fine.amount + damage_fine.amount)
                      if self._fine else damage_fine)
        self._events.append(DamageFineAdded(self._id, damage_fine, now))

    def record_reminder(self, now):
        if not self._state.is_final:
            self._events.append(ReminderSent(self._id, now))

    # ─── Приватные сеттеры для state-классов ───
    def _set_return(self, returned_on, fine):
        self._returned_on = returned_on
        self._fine = fine

    def _update_due_on(self, new_due_on):
        self._period = LoanPeriod(self._period.issued_on, new_due_on)

    # ─── Сериализация ───
    def to_state(self):
        return {
            "id": self.id.value,
            "book_id": self.book_id.value,
            "reader_id": self.reader_id.value,
            "issued_on": self._period.issued_on,
            "due_on": self._period.due_on,
            "state": type(self._state).__name__,
            "returned_on": self._returned_on,
            "fine": str(self._fine.amount) if self._fine else None,
            "events": [
                {"type": type(e).__name__,
                 **{f: getattr(e, f) for f in e.__dataclass_fields__}}
                for e in self._events
            ],
        }


# ─── Агрегат Book (без изменений) ────────────────────────────

class Book:
    def __init__(self, book_id, title, total_copies, available_copies=None):
        available = total_copies if available_copies is None else available_copies
        if not isinstance(book_id, BookId) or not isinstance(title, str) or not title.strip():
            raise DomainInvariantViolation("У книги должны быть ID и название")
        if type(total_copies) is not int or type(available) is not int:
            raise DomainInvariantViolation("Количество экземпляров должно быть целым")
        if total_copies < 1 or not 0 <= available <= total_copies:
            raise DomainInvariantViolation("Недопустимое количество экземпляров")
        self._id = book_id
        self._title = title
        self._total_copies = total_copies
        self._available_copies = available

    @property
    def id(self): return self._id
    @property
    def title(self): return self._title
    @property
    def total_copies(self): return self._total_copies
    @property
    def available_copies(self): return self._available_copies

    def checkout_copy(self):
        if self._available_copies == 0:
            raise DomainInvariantViolation("Нет свободных экземпляров")
        self._available_copies -= 1

    def accept_return(self):
        if self._available_copies >= self._total_copies:
            raise DomainInvariantViolation("Все экземпляры уже доступны")
        self._available_copies += 1

    def to_state(self):
        return {"id": self.id.value, "title": self.title,
                "total_copies": self.total_copies,
                "available_copies": self.available_copies}


# ─── Фабрики ─────────────────────────────────────────────────

class BookFactory:
    @staticmethod
    def restore(state):
        return Book(BookId(state["id"]), state["title"],
                    state["total_copies"], state["available_copies"])


_EVENT_FACTORY = {
    "LoanIssued": LoanIssued,
    "CheckoutDenied": CheckoutDenied,
    "ReservationExpired": ReservationExpired,
    "LoanExtended": LoanExtended,
    "ExtensionDenied": ExtensionDenied,
    "ReminderSent": ReminderSent,
    "BookReturned": BookReturned,
    "DamageFineAdded": DamageFineAdded,
    "DueDateExpired": DueDateExpired,
    "EscalatedToAdmin": EscalatedToAdmin,
}


class LoanFactory:
    @staticmethod
    def restore(state):
        loan = Loan(
            LoanId(state["id"]),
            BookId(state["book_id"]),
            ReaderId(state["reader_id"]),
            LoanPeriod(state["issued_on"], state["due_on"]),
        )
        loan._state = _STATE_FACTORY[state["state"]]()
        loan._returned_on = state.get("returned_on")
        if state.get("fine"):
            loan._fine = Fine(state["fine"])
        loan._events = [
            _EVENT_FACTORY[e["type"]](
                **{k: v for k, v in e.items() if k != "type"}
            )
            for e in state.get("events", [])
        ]
        return loan


# ─── Репозитории ─────────────────────────────────────────────

class BookRepository(Protocol):
    def get(self, book_id): ...
    def save(self, book): ...


class LoanRepository(Protocol):
    def get(self, loan_id): ...
    def save(self, loan): ...
    def find_open_by_book(self, book_id): ...


class InMemoryBookRepository:
    def __init__(self): self._data = {}
    def get(self, book_id):
        if book_id.value not in self._data:
            raise AggregateNotFound("Книга не найдена")
        return BookFactory.restore(self._data[book_id.value])
    def save(self, book):
        self._data[book.id.value] = book.to_state()


_OPEN_STATES = {"Registered", "Issued", "Extended", "Overdue"}


class InMemoryLoanRepository:
    def __init__(self): self._data = {}
    def get(self, loan_id):
        if loan_id.value not in self._data:
            raise AggregateNotFound("Выдача не найдена")
        return LoanFactory.restore(self._data[loan_id.value])
    def save(self, loan):
        self._data[loan.id.value] = loan.to_state()
    def find_open_by_book(self, book_id):
        return [LoanFactory.restore(s) for s in self._data.values()
                if s["book_id"] == book_id.value and s["state"] in _OPEN_STATES]


# ─── Прикладной сервис: LibraryProcess ───────────────────────

@dataclass(frozen=True)
class InspectionResult:
    """Результат задачи человека — осмотр книги."""
    has_damage: bool
    damage_fine: Fine | None = None


class LibraryProcess:
    """Прикладной сервис процесса. Один метод на задачу/шлюз BPMN."""

    def __init__(self, books: BookRepository, loans: LoanRepository, clock: Clock):
        self._books = books
        self._loans = loans
        self._clock = clock

    # ═══ Задачи BPMN ═══

    def reserve_book(self, book_id, reader_id, loan_id, period):
        """Задача «Забронировать книгу» — создаёт агрегат в начальном состоянии."""
        self._books.get(book_id)  # 404, если книги нет
        loan = Loan(loan_id, book_id, reader_id, period)
        self._loans.save(loan)
        return loan

    def check_unpaid_fines(self, reader_id):
        """Задача «Проверить непогашенные штрафы» — ветвь A параллельного блока."""
        return False  # заглушка: репозиторий штрафов пока не реализован

    def check_overdue_loans(self, reader_id):
        """Задача «Проверить просроченные книги» — ветвь B параллельного блока."""
        return False  # заглушка

    def has_debt(self, reader_id):
        """Шлюз «Есть задолженность?». Обе ветви выполнены ДО вызова (3.2.4)."""
        return (self.check_unpaid_fines(reader_id)
                or self.check_overdue_loans(reader_id))

    def issue_book(self, loan_id, book_id, now):
        """Задача «Выдать книгу» — Registered → Issued, инкремент available."""
        loan = self._loans.get(loan_id)
        book = self._books.get(book_id)
        loan.pickup(now)
        book.checkout_copy()
        self._loans.save(loan)
        self._books.save(book)

    def deny_checkout(self, loan_id, now):
        """Задача «Отказать в выдаче» — self-loop в Registered."""
        loan = self._loans.get(loan_id)
        loan.deny_debt(now)
        self._loans.save(loan)

    def request_debt_payment(self, reader_id):
        """Задача «Запросить погашение задолженности» — уведомление, без изменений."""
        pass

    def expire_reservation(self, loan_id, now):
        """Таймер «3 раб. дня» — Registered → Снята/Перенесена."""
        loan = self._loans.get(loan_id)
        has_queue = self.has_queue(loan.book_id, excluding_reader_id=loan.reader_id)
        loan.expire_reservation(has_queue, now)
        self._loans.save(loan)

    def return_to_fund(self, book_id):
        """Задача «Вернуть в фонд» — бронь снята, книга снова в фонде."""
        # Экземпляр не выдавался, инкремент не нужен
        pass

    def move_to_next_reader(self, book_id, next_reader_id, period, now):
        """Задача «Перенести бронь» — новая бронь следующему в очереди."""
        new_loan_id = LoanId(f"{book_id.value}-next-{now.timestamp()}")
        self.reserve_book(book_id, next_reader_id, new_loan_id, period)

    def send_reminder(self, loan_id, now):
        """Задача «Отправить напоминание» — непрерывающий таймер, журнал."""
        loan = self._loans.get(loan_id)
        loan.record_reminder(now)
        self._loans.save(loan)

    def request_extension(self, loan_id):
        """Шлюз «Клиент запросил продление?» — True, если разрешено."""
        return "extend" in self._loans.get(loan_id).allowed_events

    def has_queue(self, book_id, excluding_reader_id=None):
        """Шлюз «Есть очередь?» — есть другие активные брони."""
        for loan in self._loans.find_open_by_book(book_id):
            if (loan.status == "Забронирована"
                    and loan.reader_id != excluding_reader_id):
                return True
        return False

    def extend_loan(self, loan_id, new_due_on, now):
        """Задача «Продлить срок» — Issued → Extended."""
        loan = self._loans.get(loan_id)
        loan.extend(new_due_on, now)
        self._loans.save(loan)

    def deny_extension(self, loan_id, now):
        """Задача «Отказать в продлении» — self-loop в Issued."""
        loan = self._loans.get(loan_id)
        loan.extend_denied(now)
        self._loans.save(loan)

    def check_overdue(self, loan_id, returned_on):
        """Задача «Проверить просрочку» — ветвь A параллельного блока приёмки."""
        return self._loans.get(loan_id).check_overdue(returned_on)

    def inspect_book(self, damage_report):
        """Задача «Осмотреть книгу» — человек передаёт результат."""
        return damage_report

    def has_damage(self, damage_report):
        """Шлюз «Есть повреждения?»."""
        return damage_report is not None and damage_report.has_damage

    def receive_book(self, loan_id, returned_on, damage_report, rate, now):
        """Задача «Принять книгу» — обе ветви уже выполнены, переход в Returned."""
        loan = self._loans.get(loan_id)
        book = self._books.get(loan.book_id)
        loan.return_book(returned_on, rate, now)
        if self.has_damage(damage_report) and damage_report.damage_fine:
            loan.add_damage_fine(damage_report.damage_fine, now)
        book.accept_return()
        self._loans.save(loan)
        self._books.save(book)
        return loan.fine

    def expire_due(self, loan_id, now):
        """Таймер «Срок возврата истёк» — Issued/Extended → Overdue."""
        loan = self._loans.get(loan_id)
        loan.expire_due(now)
        self._loans.save(loan)

    def escalate_30(self, loan_id, now):
        """Таймер «30 дней после срока» — Overdue → Escalated."""
        loan = self._loans.get(loan_id)
        loan.escalate_30(now)
        self._loans.save(loan)

    # ═══ Методы on_<event> для таймеров (треб. 3.2.5) ═══

    def on_reservation_expired(self, loan_id):
        self.expire_reservation(loan_id, self._clock.now())

    def on_reminder_due(self, loan_id):
        self.send_reminder(loan_id, self._clock.now())

    def on_due_expired(self, loan_id):
        self.expire_due(loan_id, self._clock.now())

    def on_30_days_after_due(self, loan_id):
        self.escalate_30(loan_id, self._clock.now())

    # ═══ Утилита (треб. 3.2.3) ═══

    def require_condition(self, gateway_name, *conditions):
        if not any(conditions):
            raise GatewayUnresolved(gateway_name)