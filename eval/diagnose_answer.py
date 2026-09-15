"""Trace the full Ask pipeline for one question: retrieve -> score -> generate.

Shows retrieval.sufficient/score/attempts, the RAW answer-model output (before the sentinel and
citation gates), and the final Answer. This reveals whether an 'insufficient' result comes from
retrieval, from the model emitting its INSUFFICIENT_EVIDENCE sentinel, or from a missing citation.

Run against the running services:  python eval/diagnose_answer.py
"""

from __future__ import annotations

import sys

sys.path.insert(0, "backend")

from app.auth import load_demo_users  # noqa: E402
from app.generation import prompts  # noqa: E402
from app.generation.answer import generate_answer  # noqa: E402
from app.generation.llm import complete  # noqa: E402
from app.retrieval.engine import RetrievalEngine  # noqa: E402

CASES = [
    ("people_member", "how many leaves do i get?"),
    ("people_director", "What is our compensation and pay review policy?"),
]


def main() -> int:
    users = load_demo_users()
    engine = RetrievalEngine()
    for user_id, question in CASES:
        identity = users[user_id].to_identity()
        print("\n" + "=" * 78)
        print(f"USER {user_id}  Q: {question}")
        retrieval = engine.retrieve(question, identity)
        print(f"retrieval: sufficient={retrieval.sufficient} score={retrieval.evidence_score} "
              f"attempts={retrieval.attempts} chunks={len(retrieval.chunks)}")
        for c in retrieval.chunks[:5]:
            print(f"   {c.score:.3f}  {c.document_id} p{c.page}: {c.text[:90]!r}")
        if retrieval.chunks:
            raw = complete(
                prompts.answer_user_prompt(question, [c.text for c in retrieval.chunks]),
                prompts.answer_system_prompt(),
                purpose="answer",
            )
            print(f"\n   RAW MODEL OUTPUT:\n   {raw.text[:500]!r}")
        answer = generate_answer(question, retrieval, {c.document_id: c.document_id for c in retrieval.chunks})
        print(f"\n   FINAL: sufficient={answer.sufficient} citations={len(answer.citations)}")
        print(f"   TEXT: {answer.text[:300]!r}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
