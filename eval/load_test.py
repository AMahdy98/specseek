"""Latency measurement for POST /v1/query against a running API.

Not a stress test: the free-tier LLM allows 15 requests per minute, so this measures what
one request costs and what happens to latency under modest concurrency, while staying
under that limit (otherwise we would be measuring the provider's throttling).

    uv run python -m eval.load_test                    # default plan, about 6 minutes
    uv run python -m eval.load_test --sequential 6 --burst 0   # a quick trial

Each request costs one embedding and one LLM call of the daily quota.
"""

import argparse
import asyncio
import json
import math
import sys
import time
from datetime import UTC, datetime

import httpx

from eval.run_eval import EVAL_DIR, load_questions

PERF_DIR = EVAL_DIR / "perf"
PROVIDER_LIMIT_PER_MINUTE = 15
SEQUENTIAL_INTERVAL_S = 5.0  # one request every 5 s = 12 per minute
COOL_DOWN_S = 65.0  # let the provider's per-minute window empty before and between bursts
STAGES = ("embed", "search", "generate")


# ---------------------------------------------------------------- pure helpers (unit-tested)


def percentile(values: list[float], p: float) -> float:
    """Nearest-rank percentile: the smallest value with at least p% of the data at or below it.

    p50 of [1, 2, 3, 4] is 2; p95 of 20 values is the 19th smallest. No interpolation, so
    the result is always a latency that was actually observed.
    """
    if not values:
        raise ValueError("no values")
    ordered = sorted(values)
    rank = max(1, math.ceil(p / 100 * len(ordered)))
    return ordered[rank - 1]


def parse_server_timing(header: str) -> dict[str, float]:
    """'embed;dur=312, search;dur=3' -> {'embed': 312.0, 'search': 3.0}."""
    timings: dict[str, float] = {}
    for part in header.split(","):
        name, _, rest = part.strip().partition(";")
        for attribute in rest.split(";"):
            key, _, value = attribute.strip().partition("=")
            if key == "dur" and name:
                timings[name] = float(value)
    return timings


def summarize(samples: list[dict]) -> dict:
    """p50 / p95 / min / max of total latency and of each stage, over successful requests."""
    ok = [s for s in samples if s["status"] == 200]
    summary: dict = {"requests": len(samples), "ok": len(ok), "failed": len(samples) - len(ok)}
    series = {"total": [s["total_ms"] for s in ok]}
    for stage in STAGES:
        series[stage] = [s["server_ms"][stage] for s in ok if stage in s["server_ms"]]
    for name, values in series.items():
        if values:
            summary[name] = {
                "p50": round(percentile(values, 50)),
                "p95": round(percentile(values, 95)),
                "min": round(min(values)),
                "max": round(max(values)),
            }
    return summary


def markdown_table(phases: dict[str, dict]) -> str:
    lines = [
        "| Phase | Requests (ok) | Metric | p50 ms | p95 ms | min ms | max ms |",
        "|---|---|---|---|---|---|---|",
    ]
    for phase, summary in phases.items():
        for metric in ("total", *STAGES):
            if metric in summary:
                m = summary[metric]
                lines.append(
                    f"| {phase} | {summary['requests']} ({summary['ok']}) | {metric} | "
                    f"{m['p50']} | {m['p95']} | {m['min']} | {m['max']} |"
                )
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------- running


async def _ask(client: httpx.AsyncClient, question: str, phase: str) -> dict:
    started = time.perf_counter()
    try:
        response = await client.post("/v1/query", json={"question": question})
        status = response.status_code
        server_ms = parse_server_timing(response.headers.get("Server-Timing", ""))
        error = None if status == 200 else response.json().get("error", {}).get("message")
    except httpx.HTTPError as exc:
        status, server_ms, error = 0, {}, type(exc).__name__
    total_ms = (time.perf_counter() - started) * 1000
    return {
        "phase": phase,
        "status": status,
        "total_ms": round(total_ms, 1),
        "server_ms": server_ms,
        "error": error,
    }


async def run(base_url: str, questions: list[str], sequential: int, burst: int, bursts: int):
    samples: list[dict] = []
    timeout = httpx.Timeout(120.0, connect=5.0)
    async with httpx.AsyncClient(base_url=base_url, timeout=timeout) as client:
        (await client.get("/v1/health")).raise_for_status()
        next_question = iter(questions * 10)

        print(f"sequential: {sequential} requests, one every {SEQUENTIAL_INTERVAL_S:.0f} s")
        for index in range(sequential):
            tick = time.perf_counter()
            sample = await _ask(client, next(next_question), "sequential")
            samples.append(sample)
            print(f"  {index + 1:2}: {sample['status']} {sample['total_ms']:7.0f} ms "
                  f"{sample['server_ms']}", flush=True)  # fmt: skip
            # Pace from the start of the request, so a slow answer doesn't slow the plan twice.
            await asyncio.sleep(max(0.0, SEQUENTIAL_INTERVAL_S - (time.perf_counter() - tick)))

        for number in range(1, bursts + 1):
            if burst <= 0:
                break
            print(f"cooling down {COOL_DOWN_S:.0f} s, then burst {number}: {burst} at once")
            await asyncio.sleep(COOL_DOWN_S)
            phase = f"burst of {burst}"
            results = await asyncio.gather(
                *(_ask(client, next(next_question), phase) for _ in range(burst))
            )
            samples.extend(results)
            for sample in results:
                print(f"      {sample['status']} {sample['total_ms']:7.0f} ms "
                      f"{sample['server_ms']}", flush=True)  # fmt: skip
    return samples


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--sequential", type=int, default=24)
    parser.add_argument("--burst", type=int, default=6, help="requests sent at the same moment")
    parser.add_argument("--bursts", type=int, default=2)
    args = parser.parse_args()
    if args.burst > PROVIDER_LIMIT_PER_MINUTE:
        parser.error(f"--burst above the provider limit of {PROVIDER_LIMIT_PER_MINUTE}/min")

    questions = [
        q["question"]
        for q in load_questions(EVAL_DIR / "questions.yaml")
        if q["type"] != "unanswerable"
    ]
    samples = asyncio.run(run(args.base_url, questions, args.sequential, args.burst, args.bursts))

    phases: dict[str, dict] = {}
    for phase in dict.fromkeys(sample["phase"] for sample in samples):
        phases[phase] = summarize([s for s in samples if s["phase"] == phase])

    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    PERF_DIR.mkdir(exist_ok=True)
    out = PERF_DIR / f"{stamp}.json"
    out.write_text(
        json.dumps({"started_at": stamp, "plan": vars(args), "phases": phases, "samples": samples},
                   indent=2) + "\n",
        encoding="utf-8",
    )  # fmt: skip
    print()
    print(markdown_table(phases))
    failures = [s for s in samples if s["status"] != 200]
    for sample in failures:
        print(f"FAILED ({sample['phase']}): {sample['status']} {sample['error']}")
    print(f"raw samples: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
