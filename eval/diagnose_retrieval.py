"""Diagnose why answers come back 'insufficient': separate retrieval from judging.

For each (user, question), prints the top retrieved chunks with their similarity scores and the
document they came from, then the LLM judge's evidence score. This tells us whether the problem
is retrieval (wrong/no docs) or the judge (good docs scored low).

Run against the running services:  python eval/diagnose_retrieval.py
"""

from __future__ import annotations

import sys

sys.path.insert(0, "backend")

from app.auth import load_demo_users  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.retrieval.engine import RetrievalEngine  # noqa: E402
from app.retrieval.scoring import evaluate_evidence  # noqa: E402

CASES = [
    ("people_member", "How many days of paid annual leave do I get?"),
    ("people_member", "What is the sick leave policy?"),
    ("people_director", "What is our compensation and pay review policy?"),
    ("eng_engineer", "How do I take a Made Tech laptop abroad?"),
    ("people_member", "hi are you working"),
]


def main() -> int:
    s = get_settings()
    print(f"provider={s.embedding_provider}/{s.llm_provider}  dim={s.embedding_dim}  "
          f"top_k={s.retrieval_top_k}  threshold={s.evidence_threshold}")
    users = load_demo_users()
    engine = RetrievalEngine()

    for user_id, question in CASES:
        identity = users[user_id].to_identity()
        print("\n" + "=" * 78)
        print(f"USER {user_id} ({identity.department}/{identity.access_level})")
        print(f"Q: {question}")
        result = engine.retrieve_fixed(question, identity, judge=False)
        print(f"retrieved {len(result.chunks)} chunks:")
        for c in result.chunks:
            print(f"   score={c.score:.3f}  {c.document_id}  (p{c.page})  {c.text[:70]!r}")
        if result.chunks:
            j = evaluate_evidence(question, result.chunks)
            print(f"JUDGE score={j.score:.3f}  sufficient={j.sufficient}  missing={j.missing!r}")
            print(f"  -> {'SUFFICIENT' if j.score >= s.evidence_threshold else 'INSUFFICIENT'} "
                  f"at threshold {s.evidence_threshold}")
        else:
            print("JUDGE skipped: retrieval returned nothing (access filter or no match)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
