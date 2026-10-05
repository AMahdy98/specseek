"""Tests for the latency script's arithmetic. No network."""

import pytest

from eval.load_test import markdown_table, parse_server_timing, percentile, summarize


def test_percentile_is_nearest_rank_and_always_an_observed_value():
    values = [40, 10, 30, 20]  # unsorted on purpose
    assert percentile(values, 50) == 20
    assert percentile(values, 75) == 30
    assert percentile(values, 95) == 40
    assert percentile(values, 100) == 40
    assert percentile([7], 50) == 7 == percentile([7], 95)


def test_p95_of_twenty_values_is_the_nineteenth():
    assert percentile(list(range(1, 21)), 95) == 19
    assert percentile(list(range(1, 21)), 50) == 10


def test_percentile_of_nothing_is_an_error():
    with pytest.raises(ValueError):
        percentile([], 50)


def test_parse_server_timing():
    assert parse_server_timing("embed;dur=312, search;dur=3, generate;dur=2400") == {
        "embed": 312.0,
        "search": 3.0,
        "generate": 2400.0,
    }
    assert parse_server_timing("") == {}
    assert parse_server_timing('db;desc="x";dur=5.5') == {"db": 5.5}


def _sample(total, status=200, generate=None):
    server = {"embed": 300.0, "search": 3.0, "generate": generate or total - 303.0}
    return {"phase": "sequential", "status": status, "total_ms": total, "server_ms": server}


def test_summarize_ignores_failed_requests_in_the_latency_numbers():
    samples = [_sample(1000), _sample(2000), _sample(3000), _sample(90000, status=502)]
    summary = summarize(samples)

    assert (summary["requests"], summary["ok"], summary["failed"]) == (4, 3, 1)
    assert summary["total"] == {"p50": 2000, "p95": 3000, "min": 1000, "max": 3000}
    assert summary["search"]["p50"] == 3
    assert summary["generate"]["max"] == 2697


def test_summarize_with_no_successes_reports_counts_only():
    assert summarize([_sample(1000, status=502)]) == {"requests": 1, "ok": 0, "failed": 1}


def test_markdown_table_has_one_row_per_phase_and_metric():
    table = markdown_table({"sequential": summarize([_sample(1000), _sample(2000)])})
    assert "| sequential | 2 (2) | total | 1000 | 2000 | 1000 | 2000 |" in table
    assert "| sequential | 2 (2) | search | 3 | 3 | 3 | 3 |" in table
    assert table.count("\n") == 2 + 4  # header, separator, then total + three stages
