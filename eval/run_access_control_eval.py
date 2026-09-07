"""Run the access-control red-team suite through both transports.

Usage: python -m eval.run_access_control_eval --transport http|mcp|both

Pass criterion is strict (docs/EVALUATION.md section 1.2): an item passes only if the retrieved
context for that request contains zero chunks from the target document. Judging the answer text
alone is insufficient -- a leak the model did not quote is still a leak.
"""

from typing import Any


def load_suite(path: str) -> list[dict[str, Any]]:
    """Load the adversarial query set."""
    raise NotImplementedError


def run_via_http(item: dict[str, Any]) -> dict[str, Any]:
    """Execute one adversarial query through the REST API."""
    raise NotImplementedError


def run_via_mcp(item: dict[str, Any]) -> dict[str, Any]:
    """Execute the same query through the MCP tool interface."""
    raise NotImplementedError


def judge(item: dict[str, Any], retrieved_document_ids: list[str], answer_text: str) -> bool:
    """Return whether the item passed, using the strict context-based criterion."""
    raise NotImplementedError


def main() -> None:
    """CLI entrypoint."""
    raise NotImplementedError


# TODO:
#  1. Implement judge() against the retrieved context, and treat any appearance of
#     target_document_id as a failure regardless of the answer.
#  2. Implement run_via_http() and run_via_mcp() so they differ only in transport -- if they need
#     different judging, the trust boundary has leaked into the test.
#  3. Emit the per-item table and the summary table from docs/EVALUATION.md section 5.
#  4. Exit non-zero on any failure, so this can gate a release later.
#  5. Include the planted prompt-injection document case; assert the injected instruction did not
#     change the applied filter.
#  6. Re-run against the shipped build in Sprint 4 and keep both result files.
