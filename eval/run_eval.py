"""Evaluation runner: ask every question with both chunking strategies and save raw answers.

It calls the query service directly (no HTTP), with the real database and the real provider.
A human then grades the answers; this script only collects, lays out and counts.

    uv run --env-file .env python -m eval.run_eval run                 # all questions
    uv run --env-file .env python -m eval.run_eval run --only q01,q05  # a trial
    uv run --env-file .env python -m eval.run_eval run --resume eval/runs/<stamp>.json
    uv run python -m eval.run_eval tabulate eval/runs/<stamp>-grades.yaml

Quota: one embedding per question (reused for both strategies) and two LLM calls.
"""

import argparse
import asyncio
import json
import subprocess
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

import httpx
import yaml

from app.config import get_settings
from app.db import open_pool
from app.errors import ProviderError
from app.llm import GeminiProvider
from app.prompt import PROMPT_VERSION
from app.rag import answer_question
from app.retrieval import TOP_K

EVAL_DIR = Path(__file__).parent
RUNS_DIR = EVAL_DIR / "runs"
STRATEGIES = ("naive", "section_aware")
QUESTION_TYPES = {"direct", "table", "cross_reference", "unanswerable"}
REQUIRED_FIELDS = {"id", "type", "question", "expected", "document", "clause", "page"}
GRADES = ("correct", "partial", "wrong", "correctly_refused")
# How the question file names each document -> its title in the database.
DOCUMENT_TITLES = {
    "NPR-7150.2D": "NPR-7150.2D",
    "NASA-STD-8739.8B": "NASA-STD-8739.8B",
    "FDA-Premarket": "Content of Premarket Submissions for Device Software Functions",
    "FDA-OTS": "Off-the-Shelf Software Use in Medical Devices",
}
MAX_TRIES = 6  # per provider call, on top of the provider's own 3 quick attempts
WAIT_BETWEEN_TRIES_S = 30.0
PAUSE_BETWEEN_CALLS_S = 5.0  # stay under the free tier's per-minute generation limit


# ---------------------------------------------------------------- pure helpers (unit-tested)


def load_questions(path: Path) -> list[dict]:
    questions = yaml.safe_load(path.read_text(encoding="utf-8"))["questions"]
    seen: set[str] = set()
    for question in questions:
        missing = REQUIRED_FIELDS - set(question)
        if missing:
            raise ValueError(f"{question.get('id', '?')}: missing fields {sorted(missing)}")
        if question["id"] in seen:
            raise ValueError(f"duplicate question id {question['id']}")
        seen.add(question["id"])
        if question["type"] not in QUESTION_TYPES:
            raise ValueError(f"{question['id']}: unknown type {question['type']!r}")
        answerable = question["type"] != "unanswerable"
        if answerable and question["document"] not in DOCUMENT_TITLES:
            raise ValueError(f"{question['id']}: unknown document {question['document']!r}")
    return questions


def expected_page_retrieved(question: dict, sources: list[dict]) -> bool | None:
    """Was a passage from the expected document and page among the retrieved sources?

    An objective hint for telling a retrieval miss from a generation fault; it is NOT a
    grade. A chunk records the page it *starts* on, so a passage on page P may sit in a
    chunk that started on P-1: both count. None for unanswerable questions.
    """
    if question["type"] == "unanswerable":
        return None
    title = DOCUMENT_TITLES[question["document"]]
    pages = {question["page"], question["page"] - 1}
    return any(s["document"] == title and s["page"] in pages for s in sources)


def grading_sheet(run: dict) -> str:
    """A Markdown page a human reads while grading: expected answer next to both answers."""
    lines = [
        f"# Grading sheet for run {run['meta']['started_at']}",
        "",
        "Grade each answer in the matching `-grades.yaml` file with one of: "
        + ", ".join(f"`{g}`" for g in GRADES)
        + ".",
        "A refusal on an answerable question is `wrong`; "
        "an answer to an unanswerable one is `wrong`.",
        "",
    ]
    for entry in run["results"]:
        question = entry["question"]
        lines += [
            f"## {question['id']} ({question['type']})",
            f"**Question:** {question['question']}",
            "",
            f"**Expected** ({question['document']}, clause {question['clause']}, "
            f"p.{question['page']}): {question['expected']}",
            "",
        ]
        for strategy in STRATEGIES:
            answer = entry["answers"].get(strategy)
            if answer is None:
                lines += [f"### {strategy}: NOT RUN", ""]
                continue
            hit = {True: "yes", False: "NO", None: "n/a"}[answer["expected_page_retrieved"]]
            lines += [
                f"### {strategy} (refused: {answer['refused']}; expected page retrieved: {hit})",
                answer["answer"],
                "",
                "Sources: "
                + "; ".join(
                    f"{s['document'][:24]} | {s['clause_id'] or '-'} | p{s['page']}"
                    f" | {s['score']:.3f}"
                    for s in answer["sources"]
                ),
                "",
            ]
    return "\n".join(lines) + "\n"


def grades_template(run: dict) -> str:
    """The file the human fills in. Existing grades are never overwritten by the runner."""
    out = "# One of: " + " | ".join(GRADES) + "\n# `category` (for failures): "
    out += "table split | vocabulary mismatch | near-duplicate chunks | hallucination | "
    out += "missed refusal | wrong refusal | other\n"
    out += f"run: {run['meta']['started_at']}\ngrades:\n"
    for entry in run["results"]:
        out += f"  - id: {entry['question']['id']}\n"
        for strategy in STRATEGIES:
            out += f"    {strategy}: \n"
        out += "    category: \n    notes: \n"
    return out


def tabulate(grades: list[dict], run: dict) -> str:
    """Count the human's grades per strategy, overall and per question type."""
    types = {entry["question"]["id"]: entry["question"]["type"] for entry in run["results"]}
    hits = {
        (entry["question"]["id"], strategy): answer["expected_page_retrieved"]
        for entry in run["results"]
        for strategy, answer in entry["answers"].items()
    }
    lines = ["| Strategy | " + " | ".join(GRADES) + " | ungraded | expected page retrieved |"]
    lines.append("|---|" + "---|" * (len(GRADES) + 2))
    for strategy in STRATEGIES:
        counts = Counter(row.get(strategy) or "ungraded" for row in grades)
        unknown = set(counts) - set(GRADES) - {"ungraded"}
        if unknown:
            raise ValueError(f"unknown grade(s) for {strategy}: {sorted(unknown)}")
        answerable = [hits.get((row["id"], strategy)) for row in grades]
        answerable = [h for h in answerable if h is not None]
        lines.append(
            f"| {strategy} | "
            + " | ".join(str(counts[g]) for g in GRADES)
            + f" | {counts['ungraded']} | {sum(answerable)} of {len(answerable)} |"
        )

    lines += ["", "| Type | Strategy | " + " | ".join(GRADES) + " |"]
    lines.append("|---|---|" + "---|" * len(GRADES))
    for question_type in sorted(set(types.values())):
        rows = [row for row in grades if types.get(row["id"]) == question_type]
        for strategy in STRATEGIES:
            counts = Counter(row.get(strategy) for row in rows)
            lines.append(
                f"| {question_type} | {strategy} | "
                + " | ".join(str(counts[g]) for g in GRADES)
                + " |"
            )
    return "\n".join(lines) + "\n"


def settings_mismatch(meta: dict, current: dict) -> list[str]:
    """What differs between a saved run and the configuration we would continue it with.

    A run is only a fair comparison if every answer came from the same models, prompt and
    top-k. Resuming with anything different would silently mix two experiments.
    """
    return [
        f"{key}: run has {meta.get(key)!r}, current is {current[key]!r}"
        for key in ("generation_model", "embedding_model", "prompt_version", "top_k")
        if meta.get(key) != current[key]
    ]


# ---------------------------------------------------------------- running


class QuotaExhausted(Exception):
    pass


async def _with_retries(make_call, what: str):
    """Re-ask on a busy/overloaded provider; stop the whole run on an exhausted quota."""
    for attempt in range(1, MAX_TRIES + 1):
        try:
            return await make_call()
        except ProviderError as exc:
            if "quota exhausted" in exc.message:
                raise QuotaExhausted(exc.message) from exc
            if attempt == MAX_TRIES:
                raise
            print(f"    {what}: {exc.message}; waiting {WAIT_BETWEEN_TRIES_S:.0f}s "
                  f"(try {attempt}/{MAX_TRIES})", flush=True)  # fmt: skip
            await asyncio.sleep(WAIT_BETWEEN_TRIES_S)


def _save(run: dict, path: Path) -> None:
    path.write_text(json.dumps(run, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


async def run_questions(questions: list[dict], run: dict, run_path: Path) -> None:
    settings = get_settings()
    pool = await open_pool(settings.database_url)
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(60.0, connect=10.0)) as client:
            provider = GeminiProvider(
                settings.gemini_api_key,
                client,
                embedding_model=settings.embedding_model,
                generation_model=settings.generation_model,
            )
            done = {entry["question"]["id"]: entry for entry in run["results"]}
            for question in questions:
                entry = done.get(question["id"])
                if entry is None:
                    entry = {"question": question, "answers": {}}
                    run["results"].append(entry)
                missing = [s for s in STRATEGIES if s not in entry["answers"]]
                if not missing:
                    continue
                print(f"{question['id']}: {question['question'][:70]}", flush=True)

                text = question["question"]
                (vector,) = await _with_retries(
                    lambda text=text: provider.embed([text], kind="query"), "embed"
                )
                for strategy in missing:
                    result = await _with_retries(
                        lambda text=text, strategy=strategy, vector=vector: answer_question(
                            text, pool, provider, strategy=strategy, query_vector=vector
                        ),
                        strategy,
                    )
                    sources = [
                        {
                            "document": chunk.document_title,
                            "clause_id": chunk.clause_id,
                            "heading": chunk.heading,
                            "page": chunk.page,
                            "score": round(chunk.score, 4),
                            "content": chunk.content,
                        }
                        for chunk in result.sources
                    ]
                    entry["answers"][strategy] = {
                        "answer": result.answer,
                        "refused": result.refused,
                        "expected_page_retrieved": expected_page_retrieved(question, sources),
                        "sources": sources,
                    }
                    _save(run, run_path)  # after every answer: a crash loses nothing
                    print(f"    {strategy}: refused={result.refused}", flush=True)
                    await asyncio.sleep(PAUSE_BETWEEN_CALLS_S)
    finally:
        await pool.close()


def _git_commit() -> str:
    try:
        return subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, check=True
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def command_run(args: argparse.Namespace) -> int:
    questions = load_questions(Path(args.questions))
    unverified = [q["id"] for q in questions if not q.get("verified", False)]
    if unverified:
        print(f"WARNING: {len(unverified)} question(s) not marked verified: {unverified}")
    if args.only:
        wanted = set(args.only.split(","))
        questions = [q for q in questions if q["id"] in wanted]

    settings = get_settings()
    current = {
        "generation_model": settings.generation_model,
        "embedding_model": settings.embedding_model,
        "prompt_version": PROMPT_VERSION,
        "top_k": TOP_K,
    }
    if args.resume:
        run_path = Path(args.resume)
        run = json.loads(run_path.read_text(encoding="utf-8"))
        differences = settings_mismatch(run["meta"], current)
        if differences:
            print("REFUSING to resume: this would mix two configurations in one run.")
            for difference in differences:
                print(f"  {difference}")
            print("Start a new run instead (omit --resume), or restore the original settings.")
            return 4
    else:
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        RUNS_DIR.mkdir(exist_ok=True)
        run_path = RUNS_DIR / f"{stamp}.json"
        run = {
            "meta": {
                "started_at": stamp,
                "git_commit": _git_commit(),
                **current,
                "strategies": list(STRATEGIES),
            },
            "results": [],
        }

    try:
        asyncio.run(run_questions(questions, run, run_path))
        status = 0
    except QuotaExhausted as exc:
        print(f"STOPPED: {exc}. Continue later with: --resume {run_path}")
        status = 2
    except ProviderError as exc:
        print(f"STOPPED: {exc.message}. Continue with: --resume {run_path}")
        status = 3

    _save(run, run_path)
    sheet = run_path.with_name(run_path.stem + "-grading.md")
    sheet.write_text(grading_sheet(run), encoding="utf-8")
    grades = run_path.with_name(run_path.stem + "-grades.yaml")
    if not grades.exists():  # never overwrite a human's grades
        grades.write_text(grades_template(run), encoding="utf-8")
    answered = sum(len(entry["answers"]) for entry in run["results"])
    print(
        f"\n{answered} answers saved.\n  raw:    {run_path}\n  read:   {sheet}\n  grade:  {grades}"
    )
    return status


def command_tabulate(args: argparse.Namespace) -> int:
    grades_path = Path(args.grades)
    run_path = grades_path.with_name(grades_path.name.replace("-grades.yaml", ".json"))
    grades = yaml.safe_load(grades_path.read_text(encoding="utf-8"))["grades"]
    run = json.loads(run_path.read_text(encoding="utf-8"))
    print(tabulate(grades, run))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    commands = parser.add_subparsers(dest="command", required=True)
    run = commands.add_parser("run", help="ask the questions and save raw answers")
    run.add_argument("--questions", default=str(EVAL_DIR / "questions.yaml"))
    run.add_argument("--only", help="comma-separated question ids, e.g. q01,q05")
    run.add_argument("--resume", help="path of a run .json to continue")
    run.set_defaults(handler=command_run)
    tab = commands.add_parser("tabulate", help="count the grades in a -grades.yaml file")
    tab.add_argument("grades")
    tab.set_defaults(handler=command_tabulate)
    args = parser.parse_args()
    return args.handler(args)


if __name__ == "__main__":
    sys.exit(main())
