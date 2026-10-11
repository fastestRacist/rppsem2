import unittest
from datetime import date
from decimal import Decimal

from library import (
    Book, BookId, ReaderId, LoanId, LoanPeriod, Fine, FineRate,
    DomainInvariantViolation, InvalidValueObject, BookFactory,
    InMemoryBookRepository, InMemoryLoanRepository, LibraryService,
)


class LibraryTests(unittest.TestCase):
    def setUp(self):
        self.books = InMemoryBookRepository()
        self.loans = InMemoryLoanRepository()
        self.service = LibraryService(self.books, self.loans)
        self.book_id = BookId("book-1")
        self.reader_id = ReaderId("reader-1")
        self.books.save(Book(self.book_id, "DDD", 1))
        self.period = LoanPeriod(date(2026, 10, 1), date(2026, 10, 5))

    def test_checkout_rejects_when_no_copies_left(self):
        self.service.checkout(self.book_id, self.reader_id, LoanId("loan-1"), self.period)
        with self.assertRaises(DomainInvariantViolation):
            self.service.checkout(self.book_id, self.reader_id, LoanId("loan-2"), self.period)

    def test_late_return_calculates_fine_and_releases_copy(self):
        self.service.checkout(self.book_id, self.reader_id, LoanId("loan-1"), self.period)
        fine = self.service.return_book(LoanId("loan-1"), self.reader_id,
                                        date(2026, 10, 7), FineRate(Decimal("2")))
        self.assertEqual(fine, Fine(Decimal("4")))
        self.assertEqual(self.books.get(self.book_id).available_copies, 1)

    def test_return_twice_and_invalid_period_are_rejected(self):
        with self.assertRaises(InvalidValueObject):
            LoanPeriod(date(2026, 10, 6), date(2026, 10, 5))
        self.service.checkout(self.book_id, self.reader_id, LoanId("loan-1"), self.period)
        self.service.return_book(LoanId("loan-1"), self.reader_id,
                                 date(2026, 10, 5), FineRate(1))
        with self.assertRaises(DomainInvariantViolation):
            self.service.return_book(LoanId("loan-1"), self.reader_id,
                                     date(2026, 10, 6), FineRate(1))

    def test_restore_rechecks_book_invariants(self):
        with self.assertRaises(DomainInvariantViolation):
            BookFactory.restore({"id": "b", "title": "DDD", "total_copies": 1,
                                 "available_copies": 2})


if __name__ == "__main__":
    unittest.main()
