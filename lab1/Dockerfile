# ---------- Стадия 1: установка зависимостей ----------
FROM python:3.11-slim AS builder

WORKDIR /app

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
 && pip install --no-cache-dir -r requirements.txt


# ---------- Стадия 2: рантайм ----------
FROM python:3.11-slim

WORKDIR /app

COPY --from=builder /opt/venv /opt/venv

ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

COPY app.py .

EXPOSE 5000

CMD ["/opt/venv/bin/gunicorn", "--bind", "0.0.0.0:5000", "--workers", "2", "--preload", "app:app"]