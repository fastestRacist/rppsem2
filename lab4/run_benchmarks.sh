#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"
export PATH="$PWD/.venv/bin:$PATH"

mkdir -p results

wait_search() {
  python - <<'PY'
import time
import urllib.request
for _ in range(90):
    try:
        urllib.request.urlopen('http://localhost:8000/health', timeout=2).read()
        raise SystemExit(0)
    except Exception:
        time.sleep(1)
raise SystemExit('search не стал healthy за 90 секунд')
PY
}

# Четыре этапа по уточнению преподавателя.
for module in service_sync service_async_blocking service_async_io service_async; do
  echo "=== $module ==="
  APP_MODULE="$module" docker compose up -d --build --no-deps --force-recreate search
  wait_search

  for clients in 1 10 40 80; do
    echo "closed C=$clients"
    python load.py --mode closed --clients "$clients" --warmup 10 --duration 60 --timeout 30 --version "$module" \
      > "results/${module}_closed_C${clients}.json"
  done

  echo "open rate=5"
  python load.py --mode open --rate 5 --warmup 10 --duration 60 --timeout 30 --version "$module" \
    > "results/${module}_open_5rps.json"
done

echo "Результаты 20 замеров сохранены в results/*.json"
