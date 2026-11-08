"""Нагрузочный тест: closed/open, warm-up, /health каждые 100 мс, перцентили."""
from __future__ import annotations

import argparse
import asyncio
import json
import math
import random
import time
from collections import defaultdict

import httpx


def nearest_rank(values: list[float], percentile: float):
    if not values:
        return None
    ordered = sorted(values)
    index = max(0, math.ceil(percentile / 100 * len(ordered)) - 1)
    return round(ordered[index], 2)


def metrics(samples: list[tuple[float, bool]], duration: float):
    latencies = [latency for latency, _ in samples]
    errors = sum(1 for _, failed in samples if failed)
    return {
        "requests": len(samples),
        "requests_per_second": round(len(samples) / duration, 2),
        "p50_ms": nearest_rank(latencies, 50),
        "p95_ms": nearest_rank(latencies, 95),
        "p99_ms": nearest_rank(latencies, 99),
        "max_ms": round(max(latencies), 2) if latencies else None,
        "errors_percent": round(errors * 100 / len(samples), 2) if samples else None,
    }


async def run(args):
    base = args.base_url.rstrip("/")
    started = time.monotonic()
    measure_start = started + args.warmup
    measure_end = measure_start + args.duration
    request_timeout = httpx.Timeout(args.timeout)
    search_samples: list[tuple[float, bool]] = []
    health_samples: list[tuple[float, bool]] = []
    pending: set[asyncio.Task] = set()
    rng = random.Random(args.seed)

    async with httpx.AsyncClient(timeout=request_timeout) as client:
        async def request(url: str, params: dict | None, bucket: list):
            call_start = time.monotonic()
            try:
                response = await client.get(url, params=params)
                failed = response.status_code >= 400
            except (httpx.HTTPError, asyncio.TimeoutError):
                failed = True
            elapsed_ms = (time.monotonic() - call_start) * 1000
            if measure_start <= call_start < measure_end:
                bucket.append((elapsed_ms, failed))

        async def health_poller():
            while time.monotonic() < measure_end:
                cycle = time.monotonic()
                task = asyncio.create_task(request(f"{base}/health", None, health_samples))
                pending.add(task)
                task.add_done_callback(pending.discard)
                await asyncio.sleep(max(0, 0.1 - (time.monotonic() - cycle)))

        health_task = asyncio.create_task(health_poller())

        if args.mode == "closed":
            async def closed_worker():
                while time.monotonic() < measure_end:
                    await request(
                        f"{base}/search",
                        {"origin": args.origin, "destination": args.destination, "date": args.date},
                        search_samples,
                    )

            workers = [asyncio.create_task(closed_worker()) for _ in range(args.clients)]
            await asyncio.gather(*workers)
        else:
            async def open_producer():
                while time.monotonic() < measure_end:
                    task = asyncio.create_task(request(
                        f"{base}/search",
                        {"origin": args.origin, "destination": args.destination, "date": args.date},
                        search_samples,
                    ))
                    pending.add(task)
                    task.add_done_callback(pending.discard)
                    await asyncio.sleep(rng.expovariate(args.rate))

            await open_producer()

        await health_task
        if pending:
            await asyncio.gather(*list(pending), return_exceptions=True)

    output = {
        "version": args.version,
        "mode": args.mode,
        "clients": args.clients if args.mode == "closed" else None,
        "rate": args.rate if args.mode == "open" else None,
        "warmup_seconds": args.warmup,
        "measurement_seconds": args.duration,
        "client_timeout_seconds": args.timeout,
        "search": metrics(search_samples, args.duration),
        "health": metrics(health_samples, args.duration),
        "percentile_method": "nearest-rank",
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return output


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--mode", choices=("closed", "open"), required=True)
    parser.add_argument("--clients", type=int, default=10)
    parser.add_argument("--rate", type=float, default=5.0)
    parser.add_argument("--warmup", type=float, default=10.0)
    parser.add_argument("--duration", type=float, default=60.0)
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--origin", default="A00")
    parser.add_argument("--destination", default="A01")
    parser.add_argument("--date", default="2026-01-01")
    parser.add_argument("--version", default="unknown")
    parser.add_argument("--seed", type=int, default=42)
    return parser.parse_args()


if __name__ == "__main__":
    asyncio.run(run(parse_args()))
