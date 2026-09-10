"""Run the contract-review evaluation against the frozen labelled contract set.

Usage::

    python -m eval.run_contract_eval
    python -m eval.run_contract_eval --dry-run

Segmentation is scored *before* verdicts, because verdict accuracy over badly segmented input is
not interpretable: a clause the segmenter never produced cannot be classified correctly, and
counting it as a misclassification would blame the wrong component.
"""

from __future__ import annotations

import argparse
import difflib
import sys
from pathlib import Path
from typing import Any

from eval.common import (
    DATASETS_DIR,
    REPO_ROOT,
    DatasetError,
    build_provenance,
    fmt,
    load_dataset,
    login,
    markdown_table,
    write_results,
)
from eval.metrics import accuracy, confusion_matrix, macro_f1, mean

REQUIRED_FIELDS = ("contract_id", "file", "reviewed_as", "expected_clause_count", "clauses")

VERDICTS = ["Compliant", "Deviates", "Missing", "Needs Legal Review"]

#: Heading similarity above which a predicted clause is considered the same clause as a gold one.
HEADING_MATCH_RATIO = 0.6


def load_contracts(path: Path) -> list[dict[str, Any]]:
    """Load and validate the frozen contract eval set."""
    items = load_dataset(path, REQUIRED_FIELDS)
    for item in items:
        for clause in item["clauses"]:
            if clause.get("expected_verdict") not in VERDICTS:
                raise DatasetError(
                    f"{item['contract_id']}/{clause.get('clause_id')}: expected_verdict must be "
                    f"one of {VERDICTS}"
                )
        if len(item["clauses"]) != item["expected_clause_count"]:
            raise DatasetError(
                f"{item['contract_id']}: expected_clause_count is {item['expected_clause_count']} "
                f"but {len(item['clauses'])} clauses are labelled"
            )

    if not any(item.get("segmentation_path") == "llm_fallback" for item in items):
        raise DatasetError(
            "no contract in the set exercises the llm_fallback segmentation path (ADR-009). "
            "Add one, or the fallback ships untested."
        )
    return items


def align_clauses(
    predicted: list[Any], gold: list[dict[str, Any]]
) -> list[tuple[Any | None, dict[str, Any]]]:
    """Align predicted clauses to gold clauses by heading similarity.

    Every gold clause appears in the result, paired with its predicted clause or with None. An
    unmatched gold clause is a *segmentation* failure and is counted as such -- it is never
    silently dropped, which would let a segmenter improve its score by producing fewer clauses.
    """
    remaining = list(predicted)
    aligned: list[tuple[Any | None, dict[str, Any]]] = []

    for gold_clause in gold:
        gold_heading = str(gold_clause.get("heading", "")).strip().lower()
        best: Any | None = None
        best_ratio = 0.0

        for candidate in remaining:
            ratio = difflib.SequenceMatcher(
                None, gold_heading, candidate.clause.heading.strip().lower()
            ).ratio()
            if ratio > best_ratio:
                best, best_ratio = candidate, ratio

        if best is not None and best_ratio >= HEADING_MATCH_RATIO:
            remaining.remove(best)
            aligned.append((best, gold_clause))
        else:
            aligned.append((None, gold_clause))

    return aligned


def score_segmentation(
    aligned: list[tuple[Any | None, dict[str, Any]]],
    predicted_count: int,
    expected_count: int,
) -> dict[str, Any]:
    """Compute clause-count match and gold-clause match rate for one contract."""
    matched = sum(1 for predicted, _ in aligned if predicted is not None)
    return {
        "predicted_clauses": predicted_count,
        "gold_clauses": expected_count,
        "count_exact_match": predicted_count == expected_count,
        "gold_matched": matched,
        "gold_match_rate": matched / expected_count if expected_count else 0.0,
    }


def score_verdicts(all_aligned: list[tuple[Any | None, dict[str, Any]]]) -> dict[str, Any]:
    """Compute accuracy, macro-F1, the 4x4 confusion matrix, and citation accuracy.

    Citation accuracy is scored only over clauses whose verdict was correct, as specified in
    docs/EVALUATION.md: a citation attached to a wrong verdict is not a partial success.
    """
    pairs: list[tuple[str, str]] = []
    citation_hits: list[float] = []

    for predicted, gold in all_aligned:
        gold_verdict = gold["expected_verdict"]
        # An unmatched gold clause is scored as Needs Legal Review by omission: the system never
        # produced a verdict for it. It is also counted as a segmentation failure above.
        predicted_verdict = predicted.verdict.value if predicted is not None else "Needs Legal Review"
        pairs.append((gold_verdict, predicted_verdict))

        if predicted is not None and predicted_verdict == gold_verdict:
            expected_source = gold.get("expected_policy_source") or {}
            if expected_source:
                citation_hits.append(
                    float(predicted.cited_policy_doc == expected_source.get("document_id"))
                )

    matrix = confusion_matrix(pairs, VERDICTS)
    return {
        "n_clauses": len(pairs),
        "accuracy": accuracy(matrix),
        "macro_f1": macro_f1(matrix),
        "citation_accuracy": mean(citation_hits),
        "citation_scored_n": len(citation_hits),
        "confusion_matrix": matrix,
    }


def review_one(item: dict[str, Any]) -> tuple[Any, list[tuple[Any | None, dict[str, Any]]]]:
    """Review one contract and align its clauses to gold."""
    from app.auth import verify_token
    from app.contracts.reviewer import review_contract

    identity = verify_token(login(item["reviewed_as"]))
    path = REPO_ROOT / item["file"]
    result = review_contract(str(path), Path(item["file"]).name, identity)
    return result, align_clauses(result.reviews, item["clauses"])


def print_tables(summary: dict[str, Any]) -> None:
    """Print the tables from docs/EVALUATION.md section 6."""
    segmentation = summary["segmentation"]
    print("\nSegmentation:\n")
    print(
        markdown_table(
            ["Metric", "Value"],
            [
                ["Contracts evaluated", segmentation["contracts"]],
                ["Gold clauses", segmentation["gold_clauses"]],
                ["Predicted clauses", segmentation["predicted_clauses"]],
                ["Clause-count exact match (%)", fmt(100 * segmentation["count_match_rate"], 1)],
                ["Gold clauses matched (%)", fmt(100 * segmentation["gold_match_rate"], 1)],
                ["Contracts via llm_fallback", segmentation["llm_fallback_contracts"]],
            ],
        )
    )

    verdicts = summary["verdicts"]
    print("\nVerdict classification:\n")
    print(
        markdown_table(
            ["Metric", "Value"],
            [
                ["Overall accuracy", fmt(verdicts["accuracy"])],
                ["Macro-F1", fmt(verdicts["macro_f1"])],
                [
                    "Citation accuracy (on correct verdicts)",
                    f"{fmt(verdicts['citation_accuracy'])} (n={verdicts['citation_scored_n']})",
                ],
            ],
        )
    )

    print("\nConfusion matrix (rows = gold, columns = predicted):\n")
    matrix = verdicts["confusion_matrix"]
    print(
        markdown_table(
            ["gold \\ pred", *VERDICTS],
            [[gold, *[matrix[gold][pred] for pred in VERDICTS]] for gold in VERDICTS],
        )
    )


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint."""
    parser = argparse.ArgumentParser(description="Run the contract-review evaluation.")
    parser.add_argument("--dataset", default=str(DATASETS_DIR / "contracts_labeled.json"))
    parser.add_argument("--dry-run", action="store_true", help="Validate the dataset and exit.")
    args = parser.parse_args(argv)

    from app.config import get_settings
    from app.observability import configure_logging

    configure_logging(get_settings().log_level)

    dataset_path = Path(args.dataset)
    try:
        contracts = load_contracts(dataset_path)
    except DatasetError as exc:
        print(f"dataset error: {exc}", file=sys.stderr)
        return 2

    if args.dry_run:
        clauses = sum(len(item["clauses"]) for item in contracts)
        print(f"{dataset_path.name}: {len(contracts)} contracts, {clauses} labelled clauses")
        return 0

    per_item: list[dict[str, Any]] = []
    all_aligned: list[tuple[Any | None, dict[str, Any]]] = []
    segmentation_rows: list[dict[str, Any]] = []
    fallback_contracts = 0

    for item in contracts:
        result, aligned = review_one(item)
        all_aligned.extend(aligned)
        if result.segmentation_path == "llm_fallback":
            fallback_contracts += 1

        segmentation = score_segmentation(
            aligned, len(result.reviews), item["expected_clause_count"]
        )
        segmentation_rows.append(segmentation)
        per_item.append(
            {
                "contract_id": item["contract_id"],
                "reviewed_as": item["reviewed_as"],
                "segmentation_path": result.segmentation_path,
                "segmentation": segmentation,
                "clauses": [
                    {
                        "clause_id": gold.get("clause_id"),
                        "gold_verdict": gold["expected_verdict"],
                        "predicted_verdict": (
                            predicted.verdict.value if predicted is not None else None
                        ),
                        "gold_policy_doc": (gold.get("expected_policy_source") or {}).get(
                            "document_id"
                        ),
                        "cited_policy_doc": (
                            predicted.cited_policy_doc if predicted is not None else None
                        ),
                        "explanation": predicted.explanation if predicted is not None else "",
                    }
                    for predicted, gold in aligned
                ],
            }
        )

    summary = {
        "segmentation": {
            "contracts": len(contracts),
            "gold_clauses": sum(row["gold_clauses"] for row in segmentation_rows),
            "predicted_clauses": sum(row["predicted_clauses"] for row in segmentation_rows),
            "count_match_rate": mean(
                [float(row["count_exact_match"]) for row in segmentation_rows]
            ),
            "gold_match_rate": mean([row["gold_match_rate"] for row in segmentation_rows]),
            "llm_fallback_contracts": fallback_contracts,
        },
        "verdicts": score_verdicts(all_aligned),
    }

    provenance = build_provenance(
        config_label="contract-review",
        dataset_path=dataset_path,
        dataset_count=len(contracts),
    )
    path = write_results("contract_review", provenance, summary, per_item)

    print_tables(summary)
    print(f"\nresults written to {path}")
    print(
        "\nExplanation quality is graded manually against the rubric in docs/EVALUATION.md "
        "section 6; per-item explanations are in the results file."
    )
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
