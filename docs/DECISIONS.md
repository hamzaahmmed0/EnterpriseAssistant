# Architecture Decision Record

One entry per decision: context, decision, consequence. Accepted entries (ADR-001…004) come from
`docs/proposal.md` and are settled. Open entries are questions the proposal does not answer — they
must be decided deliberately and recorded here, **not** picked silently inside a call site.

Status values: `Accepted` · `Open` · `Superseded`.

---

## ADR-001 — Access control as native Qdrant pre-filtering, not post-hoc filtering

**Status:** Accepted (proposal §5, §15)

**Context.** Documents carry a department and an access level. A retrieval system can enforce that
either by filtering results after the vector search returns them, or by passing a filter into the
search so restricted vectors are never candidates. Post-hoc filtering is easier to bolt on and is
what most RAG tutorials do, but it means unauthorized chunks exist in process memory and are one
mistake — a forgotten filter, a debug log, a reranker that runs before the filter — away from the
LLM context window. It also silently degrades result quality: filtering after top-k means an
authorized user can get fewer than k results, or none, because restricted chunks consumed the slots.

**Decision.** The caller's authenticated identity is translated into a Qdrant `Filter` and passed
into the search call itself. One function builds the filter; retrieval is not callable without one.
No code path filters a result list by an `allowed` flag.

**Consequence.** Unauthorized content never enters the context window, and top-k is k *authorized*
chunks. Cost: `department` and `access_level` must be present on every Qdrant payload at ingest
time (asserted, not assumed), and the identity has to be threaded from the API boundary all the way
into the engine. Any future retrieval mode — hybrid search, reranking — must apply the filter at
the search layer too, not after.

---

## ADR-002 — MCP is a transport, not a trust boundary

**Status:** Accepted (proposal §5, §13, §15)

**Context.** The engine is exposed both as a REST API and as an MCP server. The tempting shortcut
is to treat MCP callers as "internal" and let tools call the engine directly with elevated or
implicit permissions, since the MCP client is usually a developer tool.

**Decision.** MCP tools require the caller's authenticated identity and go through the exact same
access-control path as HTTP requests. No separate code path, no bypass flag, no "trusted client"
mode. The access-control red-team suite runs through both transports and both results are reported.

**Consequence.** Adding a transport does not add an audit surface — one enforcement path to test
and to prove. Cost: MCP tool signatures must carry identity explicitly, which is slightly clumsier
than an ambient session, and the red-team suite has to be run twice.

---

## ADR-003 — Fixed-size chunking with overlap for the general corpus

**Status:** Accepted in approach (proposal §6); **parameters open**

**Context.** The corpus is policies, SOPs, and handbooks. Options were fixed-size chunking with
overlap, semantic/recursive splitting, or structure-aware splitting on headings.

**Decision.** Fixed-size chunking with overlap for general documents; clause-level segmentation is
used only for contracts (ADR-009). Chunk size and overlap are config values, not constants.

**Consequence.** Simple, predictable, and cheap to sweep during calibration. Cost: chunk boundaries
will sometimes split a policy clause across two chunks, which the overlap only partly mitigates —
a plausible failure mode for exact-identifier questions, and worth checking when reading eval
errors.

**OPEN QUESTION.** Exact `CHUNK_SIZE_TOKENS` and `CHUNK_OVERLAP_TOKENS`. The proposal does not
specify them. Decide before Sprint 1 task 1.5 and record the chosen values plus the reasoning here.
Related: whether chunk size is measured in tokens or characters, and which tokenizer defines it.

---

## ADR-004 — Bounded adaptive retrieval loop with an "insufficient evidence" terminal state

**Status:** Accepted in approach (proposal §4, §8, §11); **threshold and scoring function open**

**Context.** Single-shot RAG generates an answer whether or not the retrieved evidence supports
one. An agentic loop can score its own evidence and retry with a reformulated query — but an
unbounded loop can spin, and a loop with no honest exit will eventually generate something
ungrounded.

**Decision.** A LangGraph loop: retrieve → score evidence → if below threshold, reformulate and
retry → generate. A hard cap of 2–3 attempts. When the cap is exhausted, the system returns
"insufficient evidence" as a first-class, tested output — not an error, and never an answer from
parametric knowledge.

**Consequence.** Termination is guaranteed and the failure mode is honest. Cost: added latency on
hard queries, which must be measured and reported as part of the comparative study rather than
hidden.

**OPEN QUESTIONS.**
1. How is the evidence score defined? Candidates: mean top-k similarity, max similarity, a
   score-gap heuristic, or an LLM-as-judge sufficiency call. Each has a different latency cost and
   a different calibration story. Decide before Sprint 2 task 2.6.
2. What is the threshold value? To be calibrated on the frozen Q&A set in Sprint 2 task 2.9 — the
   *method* is decided (sweep and justify), the value is not.
3. Cap of 2 or 3 attempts? Pick after seeing how often attempt 2 changes the outcome in the sweep.
4. What does reformulation do — LLM query rewrite, keyword expansion, or top-k widening? A widened
   k is the cheapest and must still respect the access filter.

---

## ADR-005 — Local open-weight models via Ollama; no fine-tuning

**Status:** Accepted (proposal §4, §7); **model choice open**

**Context.** The project's contributions are retrieval quality, access control, and workflow
integration. Fine-tuning a model would consume most of a 4-week timeline and would not strengthen
any of those claims. Separately, a hosted API would put synthetic-but-enterprise-shaped documents
through a third party and make results dependent on a version I do not control.

**Decision.** Use a pretrained open-weight LLM (Qwen) served locally by Ollama, and an open
embedding model, as-is. No fine-tuning, no hosted API — including as a "temporary" fallback when
local inference is slow. Slow inference is reported as latency, not engineered around by changing
models mid-experiment.

**Consequence.** Results are reproducible on one machine and data never leaves it. Cost: inference
is slow, which shapes the evaluation schedule (batch runs, cached retrieval); model quality is
whatever the local model gives, so answer-accuracy numbers are lower-bounded by it.

**OPEN QUESTIONS.**
1. BGE-small vs. Nomic-embed-text for embeddings. Affects `EMBEDDING_DIM` and therefore the Qdrant
   collection schema — decide before Sprint 1 task 1.6, because changing it later means a re-ingest
   and a re-run of every result.
2. Exact Qwen tag/size. Decide before Sprint 1 task 1.8; pin it in `.env` and quote it in every
   results file.

---

## ADR-006 — Synthetic corpus and hardcoded demo users

**Status:** Accepted (proposal §3, §6, §5); **auth mechanism open**

**Context.** Demonstrating access control requires documents with genuine access boundaries and
users who sit on different sides of them. Real company documents are unavailable in an academic
setting for privacy reasons, and a real auth system (OIDC, SSO) is weeks of work that proves
nothing about the research claim.

**Decision.** Author a synthetic corpus across 2–3 departments with explicit department and access
level per document, and 3–4 hardcoded demo users spanning those boundaries. Authentication exists
only to produce a trustworthy `Identity`; authorization — the part being studied — is real.

**Consequence.** Access control is demoable live (same question, two users, different answers) and
no real data is at risk. Cost: external validity is limited — the corpus is small, clean, and
authored by the same person who wrote the questions, which is a stated limitation, not a defect to
paper over.

**OPEN QUESTIONS.**
1. Is `access_level` an ordinal scale (public < internal < confidential, higher subsumes lower) or
   an unordered tag set? This changes the shape of the Qdrant filter and every payload. Decide
   before Sprint 1 task 1.6.
2. Can a user read another department's documents at a low access level, or is department a hard
   partition? This determines what the red-team suite counts as a violation.
3. Session mechanism: signed JWT vs. opaque token vs. a plain header. Decide before Sprint 3
   task 3.1; whatever it is, the MCP path must carry the same identity.

---

## ADR-007 — Two Qdrant collections: `documents_collection` and `policy_collection`

**Status:** Accepted (proposal §14)

**Context.** Ask searches the general corpus; Check compares each contract clause against policy
text. These are different retrieval targets with different granularity needs, but a single
collection with a `type` payload field would also work.

**Decision.** Keep them as two collections, per the proposal's database design.

**Consequence.** Clean separation, and contract review cannot accidentally pull an HR handbook page
as a "policy". Cost: policy documents may need ingesting into both collections, so the ingestion
pipeline must make routing explicit and the access filter must be applied identically to both —
the filter is not collection-specific, and it must not become so.

---

## ADR-008 — Persistence in PostgreSQL, retrieval state in Qdrant

**Status:** Accepted (proposal §14); **migration tooling open**

**Context.** Users, documents metadata, conversations, messages, contract reviews, and clause
verdicts are relational; embeddings and their access payloads are vector-store concerns.

**Decision.** Follow the proposal's split exactly. Document metadata is duplicated between
PostgreSQL (`documents` table) and Qdrant payloads by design; PostgreSQL is the source of truth and
ingestion writes both.

**Consequence.** The document list view and audit trail come from PostgreSQL without touching the
vector store. Cost: the two stores can drift — ingestion must write both or neither, and a
re-ingest must be idempotent.

**OPEN QUESTION.** Alembic migrations vs. `create_all` at startup. For a 4-week academic project
with a schema that will churn, `create_all` plus a documented reset is likely enough, but the
choice should be recorded rather than assumed. Decide before Sprint 3 task 3.10.

---

## ADR-009 — Clause segmentation by structure, with an LLM fallback

**Status:** Accepted in approach (proposal §6, §8); **fallback trigger open**

**Context.** Contract review needs clause-level units, not fixed-size chunks. Structural
segmentation (section headers, numbering) is fast and deterministic but breaks on unconventional
formatting; LLM-based segmentation is robust but slow and non-deterministic.

**Decision.** Structure-first (headers/numbering), with an LLM-based classification fallback for
documents the structural pass cannot segment.

**Consequence.** Most contracts segment deterministically, which keeps the eval reproducible. Cost:
two code paths to test, and the eval set must include at least one contract that exercises the
fallback, or the fallback is untested.

**OPEN QUESTION.** What triggers the fallback — zero structural matches, a clause-count threshold,
or a clause-length heuristic? Decide before Sprint 3 task 3.4.

---

## ADR-010 — Contract output is decision support, not legal advice

**Status:** Accepted (proposal §3, §15)

**Context.** A clause-level compliance verdict reads like a legal opinion, and a user under time
pressure may treat it as one. The system is a small local model over a synthetic policy corpus.

**Decision.** Every contract-review output carries an explicit "decision support, not legal advice"
label — in the UI, in the API response body, and in the MCP tool result. The label is part of the
response contract and is tested, not a footer someone can restyle away.

**Consequence.** The claim being made is honest and the boundary is visible at every exit point.
Cost: three places to keep in sync; the MCP result in particular is easy to forget because no human
sees it directly during development.

---

## Open questions not yet assigned an ADR

Log new ones here as they surface; promote to an ADR when decided.

- Citation granularity: document + page, or document + chunk id? The ground-truth set labels
  document + page (proposal §6), so retrieval metrics need a page mapping preserved through
  chunking. Blocks Sprint 1 task 1.9.
- `RETRIEVAL_TOP_K` for generation vs. the `k=5` used for metric reporting — same value or
  decoupled? If decoupled, `precision@5` must be computed on the retrieval list, not on the
  context actually sent to the LLM.
- Exact wording of the "insufficient evidence" response. It is a tested output, so the wording is
  effectively part of the contract.
- Reranker model for Config B, if Config B survives the timeline.
- Whether the prompt-injection test document is ingested into the corpus permanently or only for
  the red-team run. Permanently is the stronger test, but it pollutes the Q&A corpus stats.
