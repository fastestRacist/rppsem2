import os
from datetime import datetime

from dotenv import load_dotenv
from flask import Flask, request
from flask_sqlalchemy import SQLAlchemy

load_dotenv()

DB_HOST = os.getenv("DB_HOST")
DB_PORT = os.getenv("DB_PORT")
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_NAME = os.getenv("DB_NAME")

DATABASE_URI = (
    f"postgresql+psycopg2://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
)

app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = DATABASE_URI
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)


class Visit(db.Model):
    """Запись об обращении клиента к приложению."""

    __tablename__ = "visits"

    id = db.Column(db.Integer, primary_key=True)
    visited_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    ip_address = db.Column(db.String(45), nullable=False)

    def __repr__(self) -> str:
        return f"<Visit id={self.id} ip={self.ip_address} at={self.visited_at}>"


# Создаём таблицу при старте приложения
with app.app_context():
    db.create_all()


@app.get("/hello")
def hello():
    """Сохраняет посещение и возвращает 'Hello' (200 OK)."""
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        ip_address = forwarded_for.split(",")[0].strip()
    else:
        ip_address = request.remote_addr or "unknown"

    visit = Visit(visited_at=datetime.utcnow(), ip_address=ip_address)
    db.session.add(visit)
    db.session.commit()

    return "Hello", 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)