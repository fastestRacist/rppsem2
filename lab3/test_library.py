import unittest
from datetime import date, datetime, timedelta
from decimal import Decimal

from library import (
    Book, BookId, ReaderId, LoanId, LoanPeriod, Fine, FineRate,
    DomainInvariantViolation, InvalidValueObject, TransitionNotAllowed,
    GatewayUnresolved, BookFactory,
    InMemoryBookRepository, InMemoryLoanRepository,
    LibraryProcess, SystemClock, InspectionResult,
)


class FakeClock:
    """Тестовые часы: время задаётся вручную."""
    def __init__(self, now):
        self._now = now
    def now(self):
        return self._now
    def set(self, now):
        self._now = now


class LibraryProcessTests(unittest.TestCase):
    def setUp(self):
        self.books = InMemoryBookRepository()
        self.loans = InMemoryLoanRepository()
        self.clock = FakeClock(datetime(2026, 10, 1, 10, 0))
        self.process = LibraryProcess(self.books, self.loans, self.clock)

        self.book_id = BookId("book-1")
        self.reader_id = ReaderId("reader-1")
        self.loan_id = LoanId("loan-1")
        self.period = LoanPeriod(date(2026, 10, 1), date(2026, 10, 5))
        self.books.save(Book(self.book_id, "DDD", 1))

    # ─── Сценарий: основной путь ───

    def test_main_path_issue_and_return(self):
        self.process.reserve_book(
            self.book_id, self.reader_id, self.loan_id, self.period)
        self.process.issue_book(self.loan_id, self.book_id,
                                self.clock.now())

        loan = self.loans.get(self.loan_id)
        self.assertEqual(loan.status, "Выдана")
        self.assertEqual(self.books.get(self.book_id).available_copies, 0)

        # Возврат вовремя
        fine = self.process.receive_book(
            self.loan_id, date(2026, 10, 5), None,
            FineRate(Decimal("2")), self.clock.now())

        self.assertEqual(fine.amount, Decimal("0"))
        self.assertEqual(self.books.get(self.book_id).available_copies, 1)
        self.assertEqual(self.loans.get(self.loan_id).status, "Возвращена")

    # ─── Инвариант: нельзя выдать, если экземпляров нет ───

    def test_no_copy_cannot_be_issued(self):
        self.process.reserve_book(
            self.book_id, self.reader_id, self.loan_id, self.period)
        self.process.issue_book(self.loan_id, self.book_id, self.clock.now())

        second_loan = LoanId("loan-2")
        self.process.reserve_book(
            self.book_id, ReaderId("reader-2"), second_loan, self.period)

        with self.assertRaises(DomainInvariantViolation):
            self.process.issue_book(second_loan, self.book_id, self.clock.now())

    # ─── Инвариант: нельзя вернуть из состояния «Забронирована» ───

    def test_return_from_registered_is_rejected(self):
        loan = self.process.reserve_book(
            self.book_id, self.reader_id, self.loan_id, self.period)

        with self.assertRaises(TransitionNotAllowed) as ctx:
            self.process.receive_book(
                self.loan_id, date(2026, 10, 3), None,
                FineRate(1), self.clock.now())
        self.assertEqual(ctx.exception.state_name, "Забронирована")
        self.assertEqual(ctx.exception.event_name, "return_book")

    # ─── Таймер: истечение брони без очереди → Снята ───

    def test_expire_reservation_without_queue(self):
        self.process.reserve_book(
            self.book_id, self.reader_id, self.loan_id, self.period)
        self.clock.set(self.clock.now() + timedelta(days=3))
        self.process.on_reservation_expired(self.loan_id)

        loan = self.loans.get(self.loan_id)
        self.assertEqual(loan.status, "Снята")
        self.assertTrue(loan.is_final)

    # ─── Таймер: истечение брони с очередью → Перенесена ───

    def test_expire_reservation_with_queue(self):
        self.process.reserve_book(
            self.book_id, self.reader_id, self.loan_id, self.period)
        # второй читатель тоже встал в очередь
        self.process.reserve_book(
            self.book_id, ReaderId("reader-2"), LoanId("loan-2"), self.period)

        self.clock.set(self.clock.now() + timedelta(days=3))
        self.process.on_reservation_expired(self.loan_id)

        self.assertEqual(self.loans.get(self.loan_id).status, "Перенесена")

    # ─── Продление и запрет второго продления ───

    def test_extension_once_then_forbidden(self):
        self.process.reserve_book(
            self.book_id, self.reader_id, self.loan_id, self.period)
        self.process.issue_book(self.loan_id, self.book_id, self.clock.now())

        new_due = date(2026, 10, 12)
        self.process.extend_loan(self.loan_id, new_due, self.clock.now())

        loan = self.loans.get(self.loan_id)
        self.assertEqual(loan.status, "Продлена")
        self.assertEqual(loan.period.due_on, new_due)

        # Второе продление — состояние Extended не переопределяет extend
        with self.assertRaises(TransitionNotAllowed):
            self.process.extend_loan(
                self.loan_id, date(2026, 10, 19), self.clock.now())

    # ─── Таймер: просрочка → Overdue, затем 30 дней → Escalated ───

    def test_overdue_then_escalated(self):
        self.process.reserve_book(
            self.book_id, self.reader_id, self.loan_id, self.period)
        self.process.issue_book(self.loan_id, self.book_id, self.clock.now())

        # Срок возврата истёк
        self.process.on_due_expired(self.loan_id)
        self.assertEqual(self.loans.get(self.loan_id).status, "Просрочена")

        # 30 дней спустя
        self.clock.set(self.clock.now() + timedelta(days=30))
        self.process.on_30_days_after_due(self.loan_id)
        self.assertEqual(self.loans.get(self.loan_id).status,
                         "Передана администрации")

    # ─── Штраф за просрочку + штраф за повреждение ───

    def test_overdue_and_damage_fines_are_summed(self):
        self.process.reserve_book(
            self.book_id, self.reader_id, self.loan_id, self.period)
        self.process.issue_book(self.loan_id, self.book_id, self.clock.now())

        damage = InspectionResult(has_damage=True,
                                  damage_fine=Fine(Decimal("50")))
        # Вернули через 2 дня после срока (просрочка 2 дня, ставка 2 → 4)
        # + 50 за повреждение = 54
        fine = self.process.receive_book(
            self.loan_id, date(2026, 10, 7), damage,
            FineRate(Decimal("2")), self.clock.now())

        self.assertEqual(fine.amount, Decimal("54"))
        self.assertEqual(self.loans.get(self.loan_id).status, "Возвращена")

    # ─── Доменные события пишутся в журнал ───

    def test_events_are_recorded(self):
        self.process.reserve_book(
            self.book_id, self.reader_id, self.loan_id, self.period)
        self.process.issue_book(self.loan_id, self.book_id, self.clock.now())
        self.process.receive_book(
            self.loan_id, date(2026, 10, 5), None,
            FineRate(2), self.clock.now())

        loan = self.loans.get(self.loan_id)
        types = [type(e).__name__ for e in loan.events]
        self.assertIn("LoanIssued", types)
        self.assertIn("BookReturned", types)

    # ─── Восстановление из состояния (фабрика) ───

    def test_restore_rechecks_book_invariants(self):
        with self.assertRaises(DomainInvariantViolation):
            BookFactory.restore({"id": "b", "title": "DDD",
                                 "total_copies": 1, "available_copies": 2})

    # ─── GatewayUnresolved ───

    def test_gateway_unresolved(self):
        with self.assertRaises(GatewayUnresolved):
            self.process.require_condition("Тестовый шлюз", False, False)


if __name__ == "__main__":
    unittest.main()