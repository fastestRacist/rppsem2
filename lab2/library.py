from dataclasses import dataclass
from datetime import date
from decimal import Decimal
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


def _non_negative_money(value, name: str) -> Decimal:
    try:
        result = Decimal(str(value))
    except Exception as exc:
        raise InvalidValueObject(f"Некорректное значение: {name}") from exc
    if not result.is_finite() or result < 0:
        raise InvalidValueObject(f"{name} не может быть отрицательным")
    return result


# Объекты-значения
@dataclass(frozen=True)
class BookId:
    value: str

    def __post_init__(self):
        _non_empty(self.value, "ID книги")


@dataclass(frozen=True)
class ReaderId:
    value: str

    def __post_init__(self):
        _non_empty(self.value, "ID читателя")


@dataclass(frozen=True)
class LoanId:
    value: str

    def __post_init__(self):
        _non_empty(self.value, "ID выдачи")


@dataclass(frozen=True)
class LoanPeriod:
    issued_on: date
    due_on: date

    def __post_init__(self):
        if type(self.issued_on) is not date or type(self.due_on) is not date:
            raise InvalidValueObject("Даты должны иметь тип date")
        if self.due_on < self.issued_on:
            raise InvalidValueObject("Срок возврата раньше даты выдачи")


@dataclass(frozen=True)
class Fine:
    amount: Decimal

    def __post_init__(self):
        object.__setattr__(self, "amount", _non_negative_money(self.amount, "Штраф"))


@dataclass(frozen=True)
class FineRate:
    amount_per_day: Decimal

    def __post_init__(self):
        object.__setattr__(self, "amount_per_day",
                           _non_negative_money(self.amount_per_day, "Ставка штрафа"))


# Агрегат 1: Book — корень агрегата книги.
class Book:
    def __init__(self, book_id: BookId, title: str, total_copies: int,
                 available_copies: int | None = None):
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
    def __init__(self, loan_id: LoanId, book_id: BookId, reader_id: ReaderId,
                 period: LoanPeriod, returned_on: date | None = None,
                 fine: Fine | None = None):
        if not all(isinstance(x, t) for x, t in (
            (loan_id, LoanId), (book_id, BookId), (reader_id, ReaderId), (period, LoanPeriod)
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

    def return_book(self, returned_on: date, rate: FineRate) -> Fine:
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
    def restore(state: dict) -> Book:
        return Book(BookId(state["id"]), state["title"],
                    state["total_copies"], state["available_copies"])


class LoanFactory:
    @staticmethod
    def restore(state: dict) -> Loan:
        fine = Fine(state["fine"]) if state["fine"] is not None else None
        return Loan(LoanId(state["id"]), BookId(state["book_id"]),
                    ReaderId(state["reader_id"]),
                    LoanPeriod(state["issued_on"], state["due_on"]),
                    state["returned_on"], fine)


# Репозитории описаны как порты Protocol.
class BookRepository(Protocol):
    def get(self, book_id: BookId) -> Book: ...
    def save(self, book: Book) -> None: ...


class LoanRepository(Protocol):
    def get(self, loan_id: LoanId) -> Loan: ...
    def save(self, loan: Loan) -> None: ...


class InMemoryBookRepository:
    def __init__(self): self._data = {}

    def get(self, book_id: BookId) -> Book:
        if book_id.value not in self._data:
            raise AggregateNotFound("Книга не найдена")
        return BookFactory.restore(self._data[book_id.value])

    def save(self, book: Book) -> None:
        self._data[book.id.value] = book.to_state()


class InMemoryLoanRepository:
    def __init__(self): self._data = {}

    def get(self, loan_id: LoanId) -> Loan:
        if loan_id.value not in self._data:
            raise AggregateNotFound("Выдача не найдена")
        return LoanFactory.restore(self._data[loan_id.value])

    def save(self, loan: Loan) -> None:
        self._data[loan.id.value] = loan.to_state()


# Доменный сервис нужен, потому что выдача и возврат меняют Book и Loan.
class LibraryService:
    def __init__(self, books: BookRepository, loans: LoanRepository):
        self._books = books
        self._loans = loans

    def checkout(self, book_id: BookId, reader_id: ReaderId,
                 loan_id: LoanId, period: LoanPeriod) -> Loan:
        book = self._books.get(book_id)
        loan = Loan(loan_id, book_id, reader_id, period)
        book.checkout_copy()
        self._books.save(book)
        self._loans.save(loan)
        return loan

    def return_book(self, loan_id: LoanId, reader_id: ReaderId,
                    returned_on: date, rate: FineRate) -> Fine:
        loan = self._loans.get(loan_id)
        if loan.reader_id != reader_id:
            raise DomainInvariantViolation("Выдача принадлежит другому читателю")
        book = self._books.get(loan.book_id)
        fine = loan.return_book(returned_on, rate)
        book.accept_return()
        self._loans.save(loan)
        self._books.save(book)
        return fine
