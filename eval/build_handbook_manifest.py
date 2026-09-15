"""Generate manifest.json for the Made Tech handbook corpus.

The handbook is ~184 Markdown files; tagging them by hand is infeasible, so this maps each file's
path to a (department, access_level) by explicit rules and writes them all into the manifest. The
tags still live only in the manifest (ADR-001) -- this authors that manifest, it does not make the
ingester infer tags from paths at run time.

Three departments: people, engineering, company. Each sensitive department has a confidential
subtree so the access-control demo has a real boundary to enforce.

Run:  python eval/build_handbook_manifest.py
"""

from __future__ import annotations

import json
from pathlib import Path

CORPUS_DIR = Path("data/corpus")

# Rules are evaluated top to bottom; first match wins. Keys are path prefixes relative to
# CORPUS_DIR (forward slashes). Value is (department, access_level).
RULES: list[tuple[str, tuple[str, str]]] = [
    # --- engineering, confidential ---
    ("guides/security", ("engineering", "confidential")),
    ("guides/it/vpn", ("engineering", "confidential")),
    # --- engineering, internal ---
    ("guides/ai", ("engineering", "internal")),
    ("guides/cloud", ("engineering", "internal")),
    ("guides/it", ("engineering", "internal")),
    ("guides/process", ("engineering", "internal")),
    ("communities-of-practice", ("engineering", "internal")),
    # --- people, confidential ---
    ("guides/compensation", ("people", "confidential")),
    # --- people, internal ---
    ("benefits", ("people", "internal")),
    ("roles", ("people", "internal")),
    ("guides/hiring", ("people", "internal")),
    ("guides/line-management", ("people", "internal")),
    ("guides/mentorship", ("people", "internal")),
    ("guides/welfare", ("people", "internal")),
    ("guides/equality-diversity-and-inclusion", ("people", "internal")),
    ("guides/learning", ("people", "internal")),
    # --- company, public ---
    ("company", ("company", "public")),
    ("team-norms", ("company", "public")),
    ("guides/office", ("company", "public")),
    ("guides/policy", ("company", "public")),
]
# Anything not matched above (e.g. guides root files) falls here.
DEFAULT = ("company", "internal")


def classify(rel_posix: str) -> tuple[str, str]:
    for prefix, tags in RULES:
        if rel_posix == prefix or rel_posix.startswith(prefix + "/"):
            return tags
    return DEFAULT


def slugify(rel_posix: str) -> str:
    """Stable document_id from the relative path (no extension)."""
    stem = rel_posix.rsplit(".", 1)[0]
    return stem.replace("/", "-").replace(" ", "-").replace("(", "").replace(")", "").lower()


def title_of(path: Path) -> str:
    """First Markdown heading, else the filename."""
    try:
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            s = line.strip()
            if s.startswith("#"):
                return s.lstrip("#").strip()[:300] or path.stem
    except OSError:
        pass
    return path.stem.replace("_", " ").replace("-", " ").title()


def main() -> None:
    files = sorted(p for p in CORPUS_DIR.rglob("*.md"))
    manifest = []
    counts: dict[tuple[str, str], int] = {}
    for path in files:
        rel = path.relative_to(CORPUS_DIR).as_posix()
        department, access_level = classify(rel)
        counts[(department, access_level)] = counts.get((department, access_level), 0) + 1
        manifest.append(
            {
                "document_id": slugify(rel),
                "title": title_of(path),
                "path": rel,
                "department": department,
                "access_level": access_level,
                "collection": "documents",
            }
        )

    out = CORPUS_DIR / "manifest.json"
    out.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"wrote {out} with {len(manifest)} entries\n")
    print("distribution (department, access_level -> count):")
    for key in sorted(counts):
        print(f"  {key[0]:12} {key[1]:12} {counts[key]}")


if __name__ == "__main__":
    main()
