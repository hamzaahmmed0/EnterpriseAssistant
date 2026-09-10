"""Shared plumbing for the three eval harnesses: provenance, dataset loading, results writing.

The provenance block is the reason this module exists. A results file that cannot say which
model, embedding, chunk size, threshold, and corpus produced it is discarded rather than
caveated (docs/EVALUATION.md), so writing results without one is made impossible here rather
than left to each harness to remember.
"""

from __future__ import annotations

import hashlib
import json
import platform
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
RESULTS_DIR = REPO_ROOT / "eval" / "results"
DATASETS_DIR = REPO_ROOT / "eval" / "datasets"


class DatasetError(Exception):
    """Raised when a dataset is missing, malformed, or fails its schema check."""


def _git(*args: str) -> str:
    """Run a git command in the repo, returning empty string if git is unavailable."""
    try:
        return subprocess.check_output(
            ["git", *args], cwd=REPO_ROOT, text=True, stderr=subprocess.DEVNULL
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return ""


def file_hash(path: Path) -> str:
    """Short content hash of a dataset file, so a run records exactly what it read."""
    if not path.exists():
        return ""
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16]


def load_dataset(path: Path, required_fields: tuple[str, ...]) -> list[dict[str, Any]]:
    """Load a JSON array dataset and check every item carries the required fields.

    Raises:
        DatasetError: If the file is missing, is not a non-empty JSON array, or any item is
            missing a required field.
    """
    if not path.exists():
        raise DatasetError(
            f"dataset not found: {path}. Author it per docs/EVALUATION.md section 1 and freeze it."
        )
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise DatasetError(f"{path.name} is not valid JSON: {exc}") from exc
    if not isinstance(raw, list) or not raw:
        raise DatasetError(f"{path.name} must be a non-empty JSON array")

    for index, item in enumerate(raw):
        missing = [field for field in required_fields if field not in item]
        if missing:
            raise DatasetError(
                f"{path.name} item {index} ({item.get('id', '?')}) is missing: {', '.join(missing)}"
            )
    return raw


def build_provenance(
    *,
    config_label: str,
    dataset_path: Path,
    dataset_count: int,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Assemble the mandatory provenance block for a results file."""
    from app.config import get_settings
    from app.generation.prompts import prompt_versions

    settings = get_settings()
    return {
        "config": {"config_label": config_label, **settings.provenance()},
        "prompt_versions": prompt_versions(),
        "dataset": {
            "name": dataset_path.name,
            "item_count": dataset_count,
            "frozen_hash": file_hash(dataset_path),
        },
        "environment": {
            "host": platform.node(),
            "python": platform.python_version(),
            "date": datetime.now(UTC).isoformat(),
            "code_commit": _git("rev-parse", "--short", "HEAD"),
            "code_dirty": bool(_git("status", "--porcelain")),
        },
        **(extra or {}),
    }


def write_results(
    name: str,
    provenance: dict[str, Any],
    aggregate: dict[str, Any],
    per_item: list[dict[str, Any]],
) -> Path:
    """Write a results file, refusing to write one without complete provenance.

    Returns:
        The path written.

    Raises:
        ValueError: If the provenance block is incomplete. Results without provenance are
            worthless, so producing one is treated as a bug, not a warning.
    """
    for section in ("config", "dataset", "environment"):
        if not provenance.get(section):
            raise ValueError(f"refusing to write results without a {section!r} provenance block")
    if not provenance["dataset"].get("frozen_hash"):
        raise ValueError("refusing to write results without the dataset hash that produced them")

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y-%m-%dT%H-%M-%SZ")
    path = RESULTS_DIR / f"{stamp}_{name}.json"
    payload = {
        "run_id": f"{stamp}_{name}",
        **provenance,
        "aggregate": aggregate,
        "per_item": per_item,
    }
    path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    return path


def login(user_id: str, password: str = "demo1234") -> str:
    """Obtain a session token for a demo user, the same way any client would.

    The harnesses authenticate rather than constructing an Identity directly: an eval that
    bypasses the auth boundary is not measuring the system that ships.
    """
    from app.auth import authenticate, issue_token

    return issue_token(authenticate(user_id, password))


def markdown_table(headers: list[str], rows: list[list[Any]]) -> str:
    """Render a Markdown table, ready to paste into docs/EVALUATION.md."""
    lines = [
        "| " + " | ".join(headers) + " |",
        "|" + "|".join(["---"] * len(headers)) + "|",
    ]
    for row in rows:
        lines.append("| " + " | ".join(str(cell) for cell in row) + " |")
    return "\n".join(lines)


def fmt(value: float, places: int = 3) -> str:
    """Format a metric for a results table."""
    return f"{value:.{places}f}"
