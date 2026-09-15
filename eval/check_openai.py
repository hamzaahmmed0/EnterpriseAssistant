"""Near-zero-cost connectivity check for the configured OpenAI provider.

Runs one tiny embedding and one tiny chat so auth / quota / model / endpoint problems surface
for a fraction of a cent, before a full corpus ingest. Prints the exact failure if any.

Run:  python eval/check_openai.py
"""

from __future__ import annotations

import sys

sys.path.insert(0, "backend")

from app.config import get_settings  # noqa: E402


def main() -> int:
    s = get_settings()
    print(f"llm_provider       : {s.llm_provider}")
    print(f"embedding_provider : {s.embedding_provider}")
    print(f"base_url           : {s.openai_base_url}")
    print(f"llm_model          : {s.openai_llm_model}")
    print(f"embedding_model    : {s.openai_embedding_model}")
    print(f"embedding_dim (cfg): {s.embedding_dim}")
    print("-" * 60)

    # 1) Embedding
    try:
        from app.ingestion.embedder import embed_query

        vec = embed_query("hello world")
        print(f"EMBED OK  -> returned {len(vec)}-dim vector")
        if len(vec) != s.embedding_dim:
            print(f"  !! dim mismatch: set EMBEDDING_DIM={len(vec)} in .env")
    except Exception as exc:  # noqa: BLE001
        print(f"EMBED FAILED -> {type(exc).__name__}: {exc}")

    # 2) Chat
    try:
        from app.generation.llm import complete

        resp = complete("Reply with the single word: ready.", purpose="probe")
        print(f"CHAT OK   -> {resp.text[:80]!r} (tokens: {resp.completion_tokens})")
    except Exception as exc:  # noqa: BLE001
        print(f"CHAT FAILED  -> {type(exc).__name__}: {exc}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
