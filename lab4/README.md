# Лабораторная работа №4. Асинхронная модель исполнения компонента

Проект — агрегатор авиабилетов: получает рейсы из собственной PostgreSQL и трёх поставщиков, объединяет результаты, строит маршруты и возвращает топ-20.

## Четыре этапа исполнения

1. `service_sync:app` — обычные `def`, блокирующие `requests`, `time.sleep` и синхронная работа с PostgreSQL. Поставщики опрашиваются последовательно.
2. `service_async_blocking:app` — обработчики заменены на `async def`, но `requests`, `time.sleep` и синхронная БД оставлены. Это демонстрирует блокировку event loop.
3. `service_async_io:app` — сетевые запросы выполняются через `httpx.AsyncClient`, ожидание повтора через `asyncio.sleep`, PostgreSQL через SQLAlchemy Async + `asyncpg`; чтение БД и три поставщика запускаются через `asyncio.gather`. Функция построения маршрутов пока расположена в этом же файле приложения.
4. `service_async:app` — тот же асинхронный I/O, что на этапе 3, но построение маршрутов вынесено из файла приложения в `route_builder.py`.

Этапы 3 и 4 имеют одинаковую стратегию ожидания I/O и одинаковый алгоритм построения маршрутов. Поэтому их время должно быть близким; возможное небольшое отличие определяется накладными расходами и шумом измерений. Само вынесение функции в отдельный файл не гарантирует ускорения CPU-вычислений.

## Категории и сортировка маршрутов

Категория определяется числом пересадок:

- `direct` — прямой маршрут;
- `one_transfer` — одна пересадка;
- `two_transfers` — две пересадки.

Маршруты сортируются по категории в указанном порядке, затем по стоимости внутри категории; после сортировки возвращаются первые 20. Это трактовка уточнения преподавателя «сортировка по категории, затем по стоимости».

Ограничения маршрута из методички: максимум две пересадки; каждый рейс вылетает в дату поиска; пересадка — в аэропорту прилёта предыдущего рейса; ожидание 1–6 часов; аэропорты не повторяются; цена равна сумме цен сегментов.

## Запуск

Нужны Docker Desktop с включённой WSL Integration (если используется WSL), Docker Engine и Docker Compose.

```bash
cp .env.example .env
docker compose up -d --build
docker compose ps
```

Сервис поиска доступен на `http://localhost:8000`.

Пример:

```bash
curl 'http://localhost:8000/search?origin=A00&destination=A01&date=2026-01-01'
curl 'http://localhost:8000/health'
```

В `docker-compose.yml` по умолчанию запускается этап 1. Переключить этапы можно так:

```bash
APP_MODULE=service_sync docker compose up -d --no-deps --force-recreate search
APP_MODULE=service_async_blocking docker compose up -d --no-deps --force-recreate search
APP_MODULE=service_async_io docker compose up -d --no-deps --force-recreate search
APP_MODULE=service_async docker compose up -d --no-deps --force-recreate search
```

## Нагрузочные замеры

`load.py` реализует:

- закрытый режим: фиксированное число клиентов, следующий запрос после ответа;
- открытый режим: запросы с интенсивностью 5 запросов/с, интервалы — экспоненциальные;
- опрос `/health` каждые 100 мс;
- p50, p95, p99, максимум, количество запросов, req/s и процент ошибок.

Для каждой из четырёх версий запускаются пять сценариев: закрытый режим C=1, 10, 40, 80 и открытый режим 5 req/s. Всего 20 измерений. Каждый замер: прогрев 10 с, измерение 60 с, тайм-аут клиента 30 с.

Из WSL или Git Bash в корне проекта:

```bash
python -m pip install -r requirements.txt
bash run_benchmarks.sh
```

JSON-результаты сохраняются в `results/`.

## Профилирование py-spy

Синхронная версия, C=10. Во время нагрузки выполнить команды записи сначала без `--idle`, затем с ним:

```bash
docker compose exec -u root search py-spy record -o /tmp/profile.svg --pid 1 --duration 60
docker compose exec -u root search py-spy record -o /tmp/profile_idle.svg --pid 1 --duration 60 --idle
docker compose cp search:/tmp/profile.svg ./profile.svg
docker compose cp search:/tmp/profile_idle.svg ./profile_idle.svg
```

Для этапа 2 (блокирующий `async def`) под нагрузкой C=10 снять стек:

```bash
APP_MODULE=service_async_blocking docker compose up -d --no-deps --force-recreate search
docker compose exec -u root search py-spy dump --pid 1
```

## Структура

- `db/init.sql` — таблица рейсов и индекс по времени вылета;
- `flight_data.py`, `seed_db.py` — детерминированная генерация и загрузка 120 дней по 1500 рейсов/сутки;
- `provider_stub.py` — три заглушки поставщиков с задержками и вероятностями ошибок из задания;
- `service_sync.py` — этап 1;
- `service_async_blocking.py` — этап 2;
- `service_async_io.py` — этап 3;
- `service_async.py` + `route_builder.py` — этап 4;
- `service_common.py` — синхронное чтение PostgreSQL и последовательный опрос поставщиков;
- `load.py`, `run_benchmarks.sh` — нагрузка и матрица 20 замеров;
- `diagrams/` — UML-диаграммы последовательного и параллельного опроса;
- `tests/` — проверки генератора и построения маршрутов.

## Проверки в среде подготовки

Проверены компиляция Python и unit-тесты. Полный запуск Docker/PostgreSQL и реальные 60-секундные замеры выполняются на машине пользователя; численные результаты в отчёте нельзя заменять расчётными предположениями.
