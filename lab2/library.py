from datetime import date
from decimal import Decimal
from typing import Protocol


# Доменные исключения
class DomainError(Exception):
    pass


class DomainInvariantViolation(DomainError):
    pass


class InvalidValueObject(DomainError):
    pass


class AggregateNotFound(DomainError):
    pass


# Вспомогательные проверки
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


# База объектов-значений
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
            f"{name.lstrip('_')}={getattr(self, name)!r}"
            for name in self.__slots__
        )
        return f"{type(self).__name__}({parts})"


# Объекты-значения
class BookId(_ValueObject):
    __slots__ = ("_value",)

    def __init__(self, value):
        _non_empty(value, "ID книги")
        self._value = value

    @property
    def value(self):
        return self._value


class ReaderId(_ValueObject):
    __slots__ = ("_value",)

    def __init__(self, value):
        _non_empty(value, "ID читателя")
        self._value = value

    @property
    def value(self):
        return self._value


class LoanId(_ValueObject):
    __slots__ = ("_value",)

    def __init__(self, value):
        _non_empty(value, "ID выдачи")
        self._value = value

    @property
    def value(self):
        return self._value


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
    def issued_on(self):
        return self._issued_on

    @property
    def due_on(self):
        return self._due_on


class Fine(_ValueObject):
    __slots__ = ("_amount",)

    def __init__(self, amount):
        self._amount = _non_negative_money(amount, "Штраф")

    @property
    def amount(self):
        return self._amount


class FineRate(_ValueObject):
    __slots__ = ("_amount_per_day",)

    def __init__(self, amount_per_day):
        self._amount_per_day = _non_negative_money(amount_per_day, "Ставка штрафа")

    @property
    def amount_per_day(self):
        return self._amount_per_day


# Агрегат 1: Book — корень агрегата книги.
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


# Агрегат 2: Loan — корень отдельной выдачи; Book хранится только по ID.
class Loan:
    def __init__(self, loan_id, book_id, reader_id, period,
                 returned_on=None, fine=None):
        if not all(isinstance(x, t) for x, t in (
            (loan_id, LoanId), (book_id, BookId),
            (reader_id, ReaderId), (period, LoanPeriod)
        )):
            raise DomainInvariantViolation("Некорректные данные выдачи")
        if returned_on is None:
            if fine is not None:
                raise DomainInvariantViolation("У незакрытой выдачи не может быть штрафа")
        else:
            if type(returned_on) is not date or returned_on < period.issued_on:
                raise DomainInvariantViolation("Возврат раньше даты выдачи")
            if not isinstance(fine, Fine):
                raise DomainInvariantViolation("Для закрытой выдачи нужен штраф")
        self._id = loan_id
        self._book_id = book_id
        self._reader_id = reader_id
        self._period = period
        self._returned_on = returned_on
        self._fine = fine

    @property
    def id(self): return self._id

    @property
    def book_id(self): return self._book_id

    @property
    def reader_id(self): return self._reader_id

    @property
    def is_open(self): return self._returned_on is None

    @property
    def fine(self): return self._fine

    def return_book(self, returned_on, rate):
        if not self.is_open:
            raise DomainInvariantViolation("Выдача уже закрыта")
        if type(returned_on) is not date or returned_on < self._period.issued_on:
            raise DomainInvariantViolation("Возврат раньше даты выдачи")
        if not isinstance(rate, FineRate):
            raise DomainInvariantViolation("Неверная ставка штрафа")
        late_days = max(0, (returned_on - self._period.due_on).days)
        self._fine = Fine(rate.amount_per_day * late_days)
        self._returned_on = returned_on
        return self._fine

    def to_state(self):
        return {"id": self.id.value, "book_id": self.book_id.value,
                "reader_id": self.reader_id.value,
                "issued_on": self._period.issued_on, "due_on": self._period.due_on,
                "returned_on": self._returned_on,
                "fine": str(self._fine.amount) if self._fine else None}


# Фабрики восстановления повторно запускают проверки конструкторов.
class BookFactory:
    @staticmethod
    def restore(state):
        return Book(BookId(state["id"]), state["title"],
                    state["total_copies"], state["available_copies"])


class LoanFactory:
    @staticmethod
    def restore(state):
        fine = Fine(state["fine"]) if state["fine"] is not None else None
        return Loan(LoanId(state["id"]), BookId(state["book_id"]),
                    ReaderId(state["reader_id"]),
                    LoanPeriod(state["issued_on"], state["due_on"]),
                    state["returned_on"], fine)


# Репозитории описаны как порты Protocol.
class BookRepository(Protocol):
    def get(self, book_id): ...
    def save(self, book): ...


class LoanRepository(Protocol):
    def get(self, loan_id): ...
    def save(self, loan): ...


class InMemoryBookRepository:
    def __init__(self): self._data = {}

    def get(self, book_id):
        if book_id.value not in self._data:
            raise AggregateNotFound("Книга не найдена")
        return BookFactory.restore(self._data[book_id.value])

    def save(self, book):
        self._data[book.id.value] = book.to_state()


class InMemoryLoanRepository:
    def __init__(self): self._data = {}

    def get(self, loan_id):
        if loan_id.value not in self._data:
            raise AggregateNotFound("Выдача не найдена")
        return LoanFactory.restore(self._data[loan_id.value])

    def save(self, loan):
        self._data[loan.id.value] = loan.to_state()


# Доменный сервис нужен, потому что выдача и возврат меняют Book и Loan.
class LibraryService:
    def __init__(self, books, loans):
        self._books = books
        self._loans = loans

    def checkout(self, book_id, reader_id, loan_id, period):
        book = self._books.get(book_id)
        loan = Loan(loan_id, book_id, reader_id, period)
        book.checkout_copy()
        self._books.save(book)
        self._loans.save(loan)
        return loan

    def return_book(self, loan_id, reader_id, returned_on, rate):
        loan = self._loans.get(loan_id)
        if loan.reader_id != reader_id:
            raise DomainInvariantViolation("Выдача принадлежит другому читателю")
        book = self._books.get(loan.book_id)
        fine = loan.return_book(returned_on, rate)
        book.accept_return()
        self._loans.save(loan)
        self._books.save(book)
        return fine