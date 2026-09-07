"""Run the Q&A evaluation for one retrieval configuration and write a results file.

Usage: python -m eval.run_retrieval_eval --config A|B|C --dataset eval/datasets/qa_ground_truth.json

The output file carries the full provenance block from docs/EVALUATION.md section 1.4. A run that
cannot record its config must not write a results file at all.
"""

from typing import Any


def load_dataset(path: str) -> list[dict[str, Any]]:
    """Load and validate the frozen ground-truth Q&A set."""
    raise NotImplementedError


def run_item(item: dict[str, Any]) -> dict[str, Any]:
    """Execute one question as its labeled user and collect per-item results."""
    raise NotImplementedError


def aggregate(per_item: list[dict[str, Any]]) -> dict[str, Any]:
    """Compute aggregate and per-question-type metrics."""
    raise NotImplementedError


def write_results(config_label: str, per_item: list[dict[str, Any]],
                  aggregate_metrics: dict[str, Any]) -> str:
    """Write the results file with its provenance block. Returns the output path."""
    raise NotImplementedError


def main() -> None:
    """CLI entrypoint."""
    raise NotImplementedError


# TODO:
#  1. Implement load_dataset() with schema validation and a hard failure on an unknown
#     question_type or a missing asked_as.
#  2. Verify the dataset frozen-commit hash matches the one recorded in docs/EVALUATION.md and
#     refuse to run on a modified frozen set.
#  3. Implement run_item(): authenticate as item.asked_as, retrieve, generate, record retrieved
#     refs, citations, evidence score, attempts, and latency.
#  4. Discard one warm-up query per run so model load time does not land in the latency numbers.
#  5. Implement aggregate() including the per-question-type recall table.
#  6. Implement write_results() with settings.provenance(); never write a file without it.
#  7. Add --dry-run that prints the resolved config and exits, for checking a sweep before it runs.
#  8. Cache retrieval results per query so a generation-only re-run does not re-embed everything.
