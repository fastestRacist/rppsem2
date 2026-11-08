# Лабораторная работа №4. Асинхронная модель исполнения компонента

Проект реализует агрегатор поиска авиаперелётов и три сравниваемые версии сервиса:

- `service_sync:app` — синхронные обработчики `def`, `requests`, SQLAlchemy Core и `psycopg` (задание 3.3);
- `service_async_blocking:app` — обработчики `async def`, но блокирующие вызовы оставлены без изменений (задание 4.1);
- `service_async:app` — `httpx.AsyncClient`, асинхронный SQLAlchemy с `asyncpg`, `asyncio.gather` (задание 4.2).

## Запуск

Нужны Docker Engine с Docker Compose и Python 3.12+ на машине, где запускается нагрузочный скрипт.

```bash
cp .env.example .env
docker compose up -d --build
docker compose ps
```

После запуска сервис поиска доступен на `http://localhost:8000`.

Пример поиска (дата находится в созданном расписании: 2026-01-01 .. 2026-04-30):

```bash
curl 'http://localhost:8000/search?origin=A00&destination=A01&date=2026-01-01'
curl 'http://localhost:8000/health'
```

В `docker-compose.yml` указана версия `service_sync`. Для смены версии:

```bash
APP_MODULE=service_async_blocking docker compose up -d --force-recreate search
APP_MODULE=service_async docker compose up -d --force-recreate search
APP_MODULE=service_sync docker compose up -d --force-recreate search
```

## Нагрузочные замеры (задания 3.5, 3.6, 4.1, 4.2)

Нагрузочный скрипт реализует замкнутый режим (`--mode closed`, фиксированное число клиентов) и открытый (`--mode open`, экспоненциальные интервалы, заданная интенсивность). Во время нагрузки `/health` опрашивается каждые 100 мс. Перцентили рассчитываются методом ближайшего ранга.

Полная матрица замеров по ТЗ: 10 секунд прогрева, 60 секунд измерения, тайм-аут 30 секунд; закрытый режим C=1, 10, 40, 80 и открытый режим 5 запросов/с для каждой из трёх версий.

```bash
python -m pip install -r requirements.txt
bash run_benchmarks.sh
```

Скрипт выполняет все 15 замеров и сохраняет JSON-файлы в `results/`.

## Профилирование (задание 3.6)

Для профилирования синхронной версии сначала переключить сервис:

```bash
APP_MODULE=service_sync docker compose up -d --no-deps --force-recreate search
```

Во время каждой записи профиля в первом терминале выполнять нагрузку `C=10`:

```bash
python load.py --mode closed --clients 10 --warmup 10 --duration 60 --timeout 30 --version service_sync
```

Одновременно во втором терминале записать профиль без `--idle`:

```bash
docker compose exec -u root search py-spy record -o /tmp/profile.svg --pid 1 --duration 60
```

Повторить нагрузку и запись с `--idle`:

```bash
docker compose exec -u root search py-spy record -o /tmp/profile_idle.svg --pid 1 --duration 60 --idle
```

Скопировать оба SVG на компьютер:

```bash
docker compose cp search:/tmp/profile.svg ./profiles/profile.svg
docker compose cp search:/tmp/profile_idle.svg ./profiles/profile_idle.svg
```

Затем открыть SVG и оценить доли ожидания поставщиков, ожидания БД и построения маршрутов.

## Снимок стека (задание 4.1)

Переключить сервис на версию с блокирующими операциями:

```bash
APP_MODULE=service_async_blocking docker compose up -d --no-deps --force-recreate search
```

Во время нагрузки `C=10` в первом терминале:

```bash
python load.py --mode closed --clients 10 --warmup 10 --duration 60 --timeout 30 --version service_async_blocking
```

Во втором терминале выполнить снимок стека основного процесса:

```bash
docker compose exec -u root search py-spy dump --pid 1
```

## Структура

- `db/init.sql` — таблица и индекс по времени вылета;
- `seed_db.py`, `flight_data.py` — детерминированная генерация 120 дней по 1500 собственных рейсов в сутки;
- `provider_stub.py` — заглушка поставщика, параметры задержек и ошибок задаются переменными окружения;
- `service_sync.py`, `service_async_blocking.py`, `service_async.py` — три версии сервиса;
- `service_common.py` — общая логика синхронной версии;
- `route_builder.py` — построение маршрутов без доступа к БД и сети;
- `load.py` — нагрузочный скрипт;
- `diagrams/*.puml` — UML-диаграммы последовательного и параллельного опроса;
- `tests/` — тесты генерации расписания и правил построения маршрутов.

## Результаты проверки в среде создания проекта

Автоматически выполнено:

```bash
python -m py_compile *.py tests/*.py
python -m unittest discover -s tests -v
```

Результат: 9 тестов пройдены.

Полный запуск Docker Compose, PostgreSQL, 15 нагрузочных измерений и `py-spy` в среде создания проекта не запускался: в ней отсутствуют Docker Engine и PostgreSQL. Поэтому в отчёте эти эмпирические значения не подменяются вымышленными цифрами. После запуска проекта на машине с Docker команда `bash run_benchmarks.sh` сформирует результаты для таблицы 3.
