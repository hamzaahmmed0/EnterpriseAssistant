"""Run the contract-review evaluation against the frozen labeled contract set.

Usage: python -m eval.run_contract_eval --dataset eval/datasets/contracts_labeled.json

Segmentation is scored before verdicts, because verdict accuracy over badly segmented input
is not interpretable.
"""

from typing import Any


def load_contracts(path: str) -> list[dict[str, Any]]:
    """Load and validate the frozen contract eval set."""
    raise NotImplementedError


def align_clauses(predicted: list[dict[str, Any]],
                  gold: list[dict[str, Any]]) -> list[tuple[dict | None, dict]]:
    """Align predicted clauses to gold clauses by heading, allowing unmatched on both sides."""
    raise NotImplementedError


def score_segmentation(aligned: list[tuple[dict | None, dict]]) -> dict[str, Any]:
    """Compute clause-count match and gold-clause match rate."""
    raise NotImplementedError


def score_verdicts(aligned: list[tuple[dict | None, dict]]) -> dict[str, Any]:
    """Compute accuracy, macro-F1, the 4x4 confusion matrix, and citation accuracy."""
    raise NotImplementedError


def main() -> None:
    """CLI entrypoint."""
    raise NotImplementedError


# TODO:
#  1. Implement align_clauses(); an unmatched gold clause counts as a segmentation failure, not a
#     verdict error, and must not be silently dropped.
#  2. Implement score_segmentation() and score_verdicts() per docs/EVALUATION.md section 6.
#  3. Score citation accuracy only over clauses whose verdict was correct, as specified.
#  4. Write results with the same provenance block the retrieval harness uses.
#  5. Report how many contracts took the llm_fallback path; if that number is zero, the fallback
#     is untested and the eval set needs one more contract.
