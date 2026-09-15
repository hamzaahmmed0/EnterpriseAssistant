# Demo Script (tested)

All questions below were verified against the running local system (nomic embeddings + Qwen,
`EVIDENCE_MODE=similarity`, threshold 0.6). Password for every demo user is `demo1234`.

Answers take ~30-90s each (local Qwen writing the answer). This is expected, not a hang.

## Demo users

| Login | Department | Level |
|---|---|---|
| `people_member` (Ayesha Khan) | people | internal |
| `people_director` (Marta Silva) | people | confidential |
| `eng_engineer` (Daniel Osei) | engineering | internal |
| `eng_lead` (Priya Raman) | engineering | confidential |

## 1. Normal cited Q&A (log in as `people_member`)

These retrieve the right document and return a cited answer:

- **How much holiday do I get?**  → 38 days (taking_holiday)
- **What is the sick leave policy?**
- **What is the cycle to work scheme?**
- **How does parental leave work?**

As `eng_engineer`:

- **How do laptop replacements work?**

## 2. Access-control demo — LEVEL boundary (the headline)

Ask the **same question** as two users in the **same department**, different levels:

**Question:** *What is our compensation and pay review policy?*
- `people_director` (confidential) → **cited answer** from the salary-reviews policy
- `people_member` (internal) → **"insufficient evidence"** (the compensation doc is filtered out
  before the search — the member never retrieves it)

Second level demo, Engineering side:

**Question:** *What is the policy on taking laptops abroad?*
- `eng_lead` (confidential) → **cited answer** from the security policy
- `eng_engineer` (internal) → **"insufficient evidence"**

## 3. Honest fallback demo

Ask anything off-topic or not in the corpus, e.g.:

- **HI**  (or)  **What is the company's crypto trading policy?**

→ Returns the "insufficient evidence" response instead of inventing an answer. This is the
citation-required, context-only guarantee working.

## Known limitation (state it honestly)

Retrieval uses local `nomic-embed-text` embeddings, which are sensitive to wording. Questions that
use the handbook's own vocabulary retrieve well; a differently-worded question (e.g. "how many
leaves do I get?" instead of "how much holiday do I get?") may miss the right document and return
"insufficient evidence" even though the answer exists. The fix is stronger embeddings
(OpenAI `text-embedding-3-small`), which the codebase already supports via `EMBEDDING_PROVIDER=openai`
— pending API credits. The access-control guarantee holds regardless of embedding quality.
