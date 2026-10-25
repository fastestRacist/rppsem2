"""Flask-адаптер. Домен и прикладной слой Flask не импортируют."""
from datetime import date, datetime

from flask import Blueprint, current_app, jsonify, request

from library import (
    AggregateNotFound, Book, BookId, DomainInvariantViolation,
    Fine, FineRate, GatewayUnresolved, InspectionResult,
    InvalidValueObject, LoanId, LoanPeriod, ReaderId, TransitionNotAllowed,
)
from clock_impl import ClockShiftBackward


bp = Blueprint("library", __name__)


# ─── Хелперы доступа к сервисам ───
def _books():    return current_app.config["books"]
def _loans():    return current_app.config["loans"]
def _process():  return current_app.config["process"]
def _clock():    return current_app.config["clock"]


def _json_required():
    data = request.get_json(silent=True)
    if data is None:
        raise InvalidValueObject("Ожидался JSON")
    return data


def _parse_date(value, field):
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise InvalidValueObject(f"Некорректная дата в поле '{field}'") from exc


def _parse_dt(value):
    try:
        return datetime.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise InvalidValueObject("Некорректный ISO 8601 в поле 'now'") from exc


def _loan_view(loan):
    return {
        "id": loan.id.value,
        "book_id": loan.book_id.value,
        "reader_id": loan.reader_id.value,
        "status": loan.status,
        "allowed_events": sorted(loan.allowed_events),
        "is_final": loan.is_final,
        "fine": str(loan.fine.amount) if loan.fine else None,
        "returned_on": loan.returned_on.isoformat() if loan.returned_on else None,
        "events": [
            {"type": type(e).__name__, "at": e.at.isoformat()}
            for e in loan.events
        ],
    }


def _damage_from(payload):
    if not payload:
        return None
    fine = Fine(payload["fine"]) if payload.get("fine") else None
    return InspectionResult(has_damage=bool(payload.get("has_damage")),
                            damage_fine=fine)


# ─── Книги ───
@bp.post("/books")
def create_book():
    data = _json_required()
    book = Book(
        BookId(data["id"]),
        data["title"],
        int(data.get("total_copies", 1)),
        int(data.get("available_copies", data.get("total_copies", 1))),
    )
    _books().save(book)
    return jsonify(book.to_state()), 201


# ─── Операции процесса ───
@bp.post("/loans")
def reserve_book():
    data = _json_required()
    period = LoanPeriod(
        _parse_date(data["issued_on"], "issued_on"),
        _parse_date(data["due_on"], "due_on"),
    )
    loan = _process().reserve_book(
        BookId(data["book_id"]),
        ReaderId(data["reader_id"]),
        LoanId(data["loan_id"]),
        period,
    )
    return jsonify(_loan_view(loan)), 201


@bp.post("/loans/<loan_id>/issue")
def issue_book(loan_id):
    loan = _loans().get(LoanId(loan_id))
    _process().issue_book(LoanId(loan_id), loan.book_id, _clock().now())
    return jsonify(_loan_view(_loans().get(LoanId(loan_id)))), 200


@bp.post("/loans/<loan_id>/deny")
def deny_checkout(loan_id):
    _process().deny_checkout(LoanId(loan_id), _clock().now())
    return jsonify(_loan_view(_loans().get(LoanId(loan_id)))), 200


@bp.post("/loans/<loan_id>/extend")
def extend_loan(loan_id):
    data = _json_required()
    new_due = _parse_date(data["new_due_on"], "new_due_on")
    _process().extend_loan(LoanId(loan_id), new_due, _clock().now())
    return jsonify(_loan_view(_loans().get(LoanId(loan_id)))), 200


@bp.post("/loans/<loan_id>/return")
def receive_book(loan_id):
    data = _json_required()
    returned_on = _parse_date(data["returned_on"], "returned_on")
    rate = FineRate(data.get("fine_rate", 0))
    damage = _damage_from(data.get("damage"))
    fine = _process().receive_book(
        LoanId(loan_id), returned_on, damage, rate, _clock().now())
    return jsonify({
        "status": _loans().get(LoanId(loan_id)).status,
        "fine": str(fine.amount) if fine else "0",
    }), 200


@bp.post("/loans/<loan_id>/escalate")
def escalate(loan_id):
    _process().escalate_30(LoanId(loan_id), _clock().now())
    return jsonify(_loan_view(_loans().get(LoanId(loan_id)))), 200


@bp.get("/loans/<loan_id>")
def get_loan(loan_id):
    return jsonify(_loan_view(_loans().get(LoanId(loan_id)))), 200


# ─── Служебные ───
@bp.get("/health")
def health():
    return jsonify({"status": "ok"}), 200


@bp.post("/internal/tick")
def tick():
    data = request.get_json(silent=True) or {}
    now = _parse_dt(data["now"]) if "now" in data else _clock().now()
    if hasattr(_clock(), "shift_to"):
        _clock().shift_to(now)
    _process().tick(now)
    return jsonify({"now": now.isoformat()}), 200


# ─── Обработчик исключений (таблица 7) ───
def register_error_handlers(app):
    @app.errorhandler(TransitionNotAllowed)
    def _tna(e):
        return jsonify({"error": "TransitionNotAllowed", "message": str(e)}), 409

    @app.errorhandler(DomainInvariantViolation)
    def _div(e):
        return jsonify({"error": "DomainInvariantViolation",
                        "message": str(e)}), 422

    @app.errorhandler(InvalidValueObject)
    def _ivo(e):
        return jsonify({"error": "InvalidValueObject",
                        "message": str(e)}), 422

    @app.errorhandler(AggregateNotFound)
    def _nf(e):
        return jsonify({"error": "AggregateNotFound",
                        "message": str(e)}), 404

    @app.errorhandler(ClockShiftBackward)
    def _csb(e):
        return jsonify({"error": "ClockShiftBackward",
                        "message": str(e)}), 422

    @app.errorhandler(GatewayUnresolved)
    def _gu(e):
        return jsonify({"error": "GatewayUnresolved",
                        "message": str(e)}), 500