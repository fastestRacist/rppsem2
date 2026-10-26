"""Точка входа. Всё создаётся один раз при запуске."""
import logging
import os

from flask import Flask

from clock_impl import AppClock
from library import (
    InMemoryBookRepository, InMemoryLoanRepository, LibraryProcess,
)
from web import bp, register_error_handlers


LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=LOG_LEVEL,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)


def create_app() -> Flask:
    app = Flask(__name__)
    books = InMemoryBookRepository()
    loans = InMemoryLoanRepository()
    clock = AppClock()
    process = LibraryProcess(books, loans, clock)

    app.config["books"] = books
    app.config["loans"] = loans
    app.config["clock"] = clock
    app.config["process"] = process

    app.register_blueprint(bp)
    register_error_handlers(app)
    return app


app = create_app()


if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    app.run(host="0.0.0.0", port=port)