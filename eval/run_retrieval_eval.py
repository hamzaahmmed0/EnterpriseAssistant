"""Run the Q&A evaluation for one retrieval configuration and write a results file.

Usage::

    python -m eval.run_retrieval_eval --config A --mode fixed
    python -m eval.run_retrieval_eval --config C --mode adaptive
    python -m eval.run_retrieval_eval --config C --mode adaptive --dry-run

Requires a running stack (Qdrant, PostgreSQL, Ollama) with the corpus ingested. The output file
carries the full provenance block from docs/EVALUATION.md section 1.4; a run that cannot record
its config does not write a results file at all.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path
from typing import Any

from eval.common import (
    DATASETS_DIR,
    DatasetError,
    build_provenance,
    fmt,
    load_dataset,
    login,
    markdown_table,
    write_results,
)
from eval.metrics import (
    DEFAULT_K,
    GoldSource,
    RetrievedRef,
    citation_validity,
    fallback_correctness,
    latency_percentiles,
    mean,
    precision_at_k,
    recall_at_k,
    reciprocal_rank,
)

REQUIRED_FIELDS = (
    "id",
    "question",
    "question_type",
    "asked_as",
    "expected_answerable",
    "expected_sources",
)

QUESTION_TYPES = (
    "direct",
    "paraphrased",
    "multi_hop",
    "exact_identifier",
    "negative",
    "cross_document",
)


def load_qa_dataset(path: Path) -> list[dict[str, Any]]:
    """Load and validate the frozen ground-truth Q&A set."""
    items = load_dataset(path, REQUIRED_FIELDS)
    for item in items:
        if item["question_type"] not in QUESTION_TYPES:
            raise DatasetError(
                f"{item['id']}: unknown question_type {item['question_type']!r}; expected one of "
                f"{list(QUESTION_TYPES)}"
            )
        if item["expected_answerable"] and not item["expected_sources"]:
            raise DatasetError(f"{item['id']}: answerable item has no expected_sources")
        if not item["expected_answerable"] and item["expected_sources"]:
            raise DatasetError(
                f"{item['id']}: negative item carries expected_sources; negatives have no gold"
            )
    return items


def run_item(item: dict[str, Any]) -> dict[str, Any]:
    """Execute one question as its labelled user and collect per-item results."""
    from app.auth import verify_token
    from app.generation.answer import generate_answer
    from app.retrieval.engine import documents_engine

    identity = verify_token(login(item["asked_as"]))

    started = time.perf_counter()
    retrieval = documents_engine().retrieve(item["question"], identity)
    answer = generate_answer(item["question"], retrieval)
    latency = time.perf_counter() - started

    retrieved = [
        RetrievedRef(document_id=chunk.document_id, page=chunk.page, rank=rank)
        for rank, chunk in enumerate(retrieval.chunks, start=1)
    ]
    gold = [
        GoldSource(document_id=source["document_id"], page=int(source["page"]))
        for source in item["expected_sources"]
    ]
    cited = [
        GoldSource(document_id=citation.document_id, page=citation.page)
        for citation in answer.citations
    ]

    result: dict[str, Any] = {
        "id": item["id"],
        "question_type": item["question_type"],
        "asked_as": item["asked_as"],
        "expected_answerable": item["expected_answerable"],
        "sufficient": answer.sufficient,
        "attempts": retrieval.attempts,
        "evidence_score": retrieval.evidence_score,
        "latency_seconds": latency,
        "retrieved": [
            {"document_id": ref.document_id, "page": ref.page, "rank": ref.rank}
            for ref in retrieved
        ],
        "citations": [{"document_id": ref.document_id, "page": ref.page} for ref in cited],
        "answer": answer.text,
        # Manual grading columns, left empty for the grader to fill (docs/EVALUATION.md §2).
        "manual_answer_accuracy": None,
        "manual_groundedness": None,
    }

    if gold:
        result["precision_at_k"] = precision_at_k(retrieved, gold, DEFAULT_K)
        result["recall_at_k"] = recall_at_k(retrieved, gold, DEFAULT_K)
        result["reciprocal_rank"] = reciprocal_rank(retrieved, gold, DEFAULT_K)
        result["citation_valid"] = citation_validity(cited, retrieved, gold)
    return result


def aggregate(per_item: list[dict[str, Any]]) -> dict[str, Any]:
    """Compute aggregate and per-question-type metrics."""
    answerable = [item for item in per_item if item["expected_answerable"]]
    negatives = [item for item in per_item if not item["expected_answerable"]]

    by_type: dict[str, dict[str, Any]] = {}
    for question_type in QUESTION_TYPES:
        subset = [item for item in answerable if item["question_type"] == question_type]
        if subset:
            by_type[question_type] = {
                "n": len(subset),
                "recall_at_k": mean([item["recall_at_k"] for item in subset]),
                "precision_at_k": mean([item["precision_at_k"] for item in subset]),
            }

    negative_subset = [item for item in negatives if item["question_type"] == "negative"]
    latencies = [item["latency_seconds"] for item in per_item]

    return {
        "n_total": len(per_item),
        "n_answerable": len(answerable),
        "n_negative": len(negatives),
        "precision_at_5": mean([item["precision_at_k"] for item in answerable]),
        "recall_at_5": mean([item["recall_at_k"] for item in answerable]),
        "mrr": mean([item["reciprocal_rank"] for item in answerable]),
        "citation_validity_pct": 100 * mean([float(item["citation_valid"]) for item in answerable]),
        "fallback_correctness_pct": 100
        * fallback_correctness([item["sufficient"] for item in negative_subset]),
        "mean_attempts": mean([float(item["attempts"]) for item in per_item]),
        "latency": latency_percentiles(latencies),
        "by_question_type": by_type,
    }


def print_summary(config_label: str, summary: dict[str, Any]) -> None:
    """Print the tables ready to paste into docs/EVALUATION.md."""
    print(f"\nConfig {config_label} -- n={summary['n_total']} "
          f"({summary['n_answerable']} answerable, {summary['n_negative']} negative)\n")
    print(
        markdown_table(
            ["Metric", f"Config {config_label}"],
            [
                ["Precision@5", fmt(summary["precision_at_5"])],
                ["Recall@5", fmt(summary["recall_at_5"])],
                ["MRR", fmt(summary["mrr"])],
                ["Citation validity (%)", fmt(summary["citation_validity_pct"], 1)],
                ["Fallback correctness (%)", fmt(summary["fallback_correctness_pct"], 1)],
                ["Mean retry count", fmt(summary["mean_attempts"], 2)],
                ["Latency p50 (s)", fmt(summary["latency"]["p50"], 2)],
                ["Latency p95 (s)", fmt(summary["latency"]["p95"], 2)],
            ],
        )
    )
    print("\nPer question type (Recall@5):\n")
    print(
        markdown_table(
            ["Question type", "n", "Recall@5"],
            [
                [name, stats["n"], fmt(stats["recall_at_k"])]
                for name, stats in summary["by_question_type"].items()
            ],
        )
    )
    print("\nAnswer accuracy and groundedness are graded manually; the per-item rows carry empty "
          "columns for them (docs/EVALUATION.md section 2).")


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint."""
    parser = argparse.ArgumentParser(description="Run the Q&A retrieval evaluation.")
    parser.add_argument("--config", required=True, choices=["A", "B", "C"], help="Config label.")
    parser.add_argument(
        "--mode",
        choices=["fixed", "hybrid_rerank", "adaptive"],
        help="Retrieval mode. Defaults to the mode implied by --config (A=fixed, C=adaptive).",
    )
    parser.add_argument("--dataset", default=str(DATASETS_DIR / "qa_ground_truth.json"))
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate the dataset and print the resolved config without calling any service.",
    )
    args = parser.parse_args(argv)

    mode = args.mode or {"A": "fixed", "B": "hybrid_rerank", "C": "adaptive"}[args.config]
    # Set before app.config is imported anywhere, so the sweep controls the run.
    os.environ["RETRIEVAL_MODE"] = mode

    from app.config import get_settings, reset_settings_cache
    from app.observability import configure_logging

    reset_settings_cache()
    settings = get_settings()
    configure_logging(settings.log_level)

    dataset_path = Path(args.dataset)
    try:
        items = load_qa_dataset(dataset_path)
    except DatasetError as exc:
        print(f"dataset error: {exc}", file=sys.stderr)
        return 2

    if args.dry_run:
        print(f"config {args.config} / mode {mode}")
        print(f"dataset {dataset_path.name}: {len(items)} items, all fields present")
        for key, value in settings.provenance().items():
            print(f"  {key}: {value}")
        return 0

    # One warm-up query, discarded, so model load time does not land in the latency numbers.
    from app.generation.llm import warm_up

    warm_up()

    per_item = [run_item(item) for item in items]
    summary = aggregate(per_item)

    provenance = build_provenance(
        config_label=args.config,
        dataset_path=dataset_path,
        dataset_count=len(items),
    )
    path = write_results(f"config{args.config}_retrieval", provenance, summary, per_item)

    print_summary(args.config, summary)
    print(f"\nresults written to {path}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
