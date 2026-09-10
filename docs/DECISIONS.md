# Architecture Decision Record

One entry per decision: context, decision, consequence. ADR-001…004 come from `docs/proposal.md`.
ADR-005…013 were open questions the proposal did not answer; all are now decided and the chosen
values live in `backend/app/config.py` driven by `.env`, never inlined at a call site.

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
time (asserted in `vector_store.upsert_chunks`, not assumed), and the identity has to be threaded
from the API boundary into the engine. Any future retrieval mode must apply the filter at the
search layer too.

---

## ADR-002 — MCP is a transport, not a trust boundary

**Status:** Accepted (proposal §5, §13, §15)

**Context.** The engine is exposed both as a REST API and as an MCP server. The tempting shortcut
is to treat MCP callers as "internal" and let tools call the engine directly with elevated or
implicit permissions, since the MCP client is usually a developer tool.

**Decision.** MCP tools require the caller's session token, resolve it through the same
`auth.verify_token` the HTTP dependency uses, and go through the same access-control path. No
separate code path, no bypass flag. `department` and `access_level` are never accepted as tool
arguments — a client-supplied access level is privilege escalation by design.

**Consequence.** Adding a transport does not add an audit surface. Cost: MCP tool signatures carry
a token explicitly, and the red-team suite runs twice.

---

## ADR-003 — Fixed-size chunking with overlap, measured in tiktoken tokens

**Status:** Accepted — parameters resolved 2026-09-10

**Context.** The corpus is policies, SOPs, and handbooks. Options were fixed-size chunking with
overlap, semantic/recursive splitting, or structure-aware splitting on headings. Size also needed
a unit: characters are trivial to compute but do not correspond to model context; tokens are the
right unit but need a tokenizer, and `nomic-embed-text` (ADR-005) is served over Ollama, which
does not expose its tokenizer.

**Decision.** Fixed-size chunking with overlap for general documents; clause-level segmentation
only for contracts (ADR-009). Size is measured in **tiktoken `cl100k_base` tokens**, used purely
as a stable measuring stick — it is explicitly *not* the embedding model's own tokenizer.
Defaults: `CHUNK_SIZE_TOKENS=512`, `CHUNK_OVERLAP_TOKENS=64`.

512 leaves a whole policy clause intact in most cases while staying far inside the embedding
model's 8192-token window; 64 (12.5%) is enough to carry a sentence across a boundary without
inflating the index by much.

**Consequence.** Chunk size is comparable across runs and sweepable. Cost: `tiktoken` is a
dependency used only for counting, and token counts are approximate with respect to the actual
embedding model. Chunk boundaries will still sometimes split a clause, which the overlap only
partly mitigates — a plausible failure mode for `exact_identifier` questions and worth checking
when reading eval errors.

---

## ADR-004 — Bounded adaptive loop with LLM-as-judge evidence scoring

**Status:** Accepted — scoring function, cap, and reformulation resolved 2026-09-10

**Context.** Single-shot RAG generates an answer whether or not the retrieved evidence supports
one. An agentic loop can score its own evidence and retry with a reformulated query — but an
unbounded loop can spin, and a loop with no honest exit will eventually generate something
ungrounded. Scoring could be similarity-based (cheap, deterministic, but blind to
similar-but-irrelevant chunks) or an LLM sufficiency judgement (more accurate, slower,
non-deterministic).

**Decision.** A LangGraph loop: retrieve → judge → if insufficient, reformulate and retry →
generate. Resolved parameters:

1. **Scoring: LLM-as-judge.** `scoring.score_evidence` asks the local model, at temperature 0
   with structured JSON output, for a sufficiency score in [0,1] plus a `missing` field naming
   what the context lacks.
2. **Threshold: `EVIDENCE_THRESHOLD=0.6`** as the starting point, to be calibrated by sweep in
   Sprint 2 task 2.9. The method is decided; the final value is an experimental result.
3. **Cap: `ADAPTIVE_MAX_ATTEMPTS=3`**, checked in `route_after_score` and nowhere else.
4. **Reformulation: LLM query rewrite seeded by the judge's `missing` field.** The judge already
   states what is absent, so the rewrite targets it instead of guessing. The access filter is
   re-applied on every retry; a widened k is still k authorized chunks.

When the cap is exhausted the system returns `INSUFFICIENT_EVIDENCE_MESSAGE`
(`backend/app/generation/answer.py`) as a first-class, tested output. The exact wording is part
of the API contract and is pinned by a test.

**Consequence.** The judge catches the failure mode similarity scores miss: chunks that are
topically close but do not contain the answer. Termination is guaranteed and the failure mode is
honest.

Costs, stated plainly:

- **Latency.** Each attempt now costs a judge call plus, on retry, a rewrite call. Worst case is
  3 judge + 2 rewrite + 1 answer = 6 LLM round-trips. This is measured and reported in the
  comparative study, not hidden.
- **Reproducibility.** An LLM judge is not deterministic, which is in tension with the frozen-set
  rule in `docs/EVALUATION.md`. Mitigated three ways: temperature 0, strict JSON output, and a
  judge cache keyed on `sha256(query + sorted chunk_ids + prompt_version)` so re-running the same
  configuration over the same frozen set replays the same verdicts. The residual
  non-determinism is a stated limitation, not a solved problem.
- Bumping `CLAUSE_VERDICT_PROMPT_VERSION` or `JUDGE_PROMPT_VERSION` invalidates the cache and
  every affected result, by design.

---

## ADR-005 — nomic-embed-text via Ollama; local Qwen; no fine-tuning

**Status:** Accepted — model choice resolved 2026-09-10

**Context.** The project's contributions are retrieval quality, access control, and workflow
integration. Fine-tuning would consume most of a 4-week timeline and strengthen none of them. A
hosted API would put the corpus through a third party and make results depend on a version we do
not control. For embeddings the choice was BGE-small (384d, in-process via sentence-transformers)
or nomic-embed-text (768d, served by the Ollama container already required for the LLM).

**Decision.** No fine-tuning; open-weight models used as-is, served locally.

- **Embeddings: `nomic-embed-text` via Ollama, `EMBEDDING_DIM=768`.** One less Python runtime and
  one less multi-hundred-megabyte dependency: Ollama is already a required service, so embeddings
  and generation share it. Nomic uses task prefixes, so `embed_query` sends
  `search_query: <text>` and `embed_texts` sends `search_document: <text>`; using the document
  prefix for queries silently degrades retrieval, so the two functions stay separate.
- **LLM: `qwen2.5:7b-instruct`**, `LLM_TEMPERATURE=0`.

**Consequence.** Reproducible on one machine, no data leaves it, a single model server to operate.
Cost: 768-dimension vectors make the index roughly twice the size of BGE-small's and ingest
somewhat slower; every embedding call is an HTTP round-trip rather than an in-process tensor op,
so ingestion batches matter (`EMBEDDING_BATCH_SIZE`). Answer quality is lower-bounded by a 7B
model. Slow inference is reported as latency, never engineered around by switching to a hosted
API mid-experiment.

---

## ADR-006 — Ordinal access levels, department as a hard partition; synthetic corpus and demo users

**Status:** Accepted — access model and session mechanism resolved 2026-09-10

**Context.** Demonstrating access control requires documents with genuine boundaries and users on
different sides of them. Real corpora are unavailable for privacy reasons, and real SSO is weeks
of work that proves nothing about the research claim. The access model itself was undecided:
ranked levels or unordered tags, and whether department gates visibility at all.

**Decision.**

1. **`access_level` is ordinal**: `public` (0) < `internal` (1) < `confidential` (2). A caller at
   level *n* may read every document at level ≤ *n*. The ranking lives in one place,
   `access_filter.ACCESS_LEVEL_ORDER`.
2. **`department` is a hard partition.** An Engineering user cannot read Finance documents at any
   access level. The single exception is the reserved department `all`, for genuinely org-wide
   documents (employee handbook, code of conduct), readable by every department subject to the
   level check.
3. **Sessions** are HMAC-SHA256-signed compact tokens (`base64(payload).base64(sig)`) minted and
   verified in `auth.py` using `AUTH_SECRET`, with an `exp` claim from `AUTH_TOKEN_TTL_MINUTES`
   (default 480). No JWT library: the payload is five fields, and a stdlib `hmac` implementation
   is ~20 lines and fully auditable by a grader.
4. Corpus and users are synthetic: 2–3 departments, 10–15 documents, 3–4 demo users spanning
   both boundaries.

**Consequence.** The filter is two `must` conditions — `department in {caller_dept, "all"}` and
`access_level in visible_levels(caller_level)` — which is cheap, indexable, and easy to red-team.
A violation is unambiguous, which is what makes the pass/fail table in `docs/EVALUATION.md`
meaningful. Live demo: same question, two users, different cited answers.

Cost: external validity is limited — the corpus is small, clean, and authored by the same team
that writes the questions. That is a stated limitation, not a defect to paper over. The `all`
department is a real widening of the partition and must appear explicitly in the red-team set, or
it becomes an untested hole.

---

## ADR-007 — Two Qdrant collections: `documents_collection` and `policy_collection`

**Status:** Accepted (proposal §14)

**Context.** Ask searches the general corpus; Check compares each contract clause against policy
text. These are different retrieval targets, but a single collection with a `type` payload field
would also work.

**Decision.** Two collections, per the proposal's database design. Routing is explicit in the
ingestion manifest (`collection: documents | policy | both`), never inferred from a filename.

**Consequence.** Contract review cannot accidentally cite an HR handbook page as "policy". Cost:
policy documents are ingested into both collections, so the manifest carries the routing, and the
access filter is applied identically to both — `build_access_filter` takes no collection argument,
so it cannot become collection-specific.

---

## ADR-008 — PostgreSQL for records, Qdrant for vectors; `create_all`, no Alembic

**Status:** Accepted — migration tooling resolved 2026-09-10

**Context.** Users, document metadata, conversations, messages, contract reviews, and clause
verdicts are relational; embeddings and their access payloads are vector-store concerns. The
schema will churn weekly for four weeks.

**Decision.** Follow the proposal's split. Schema is created with `Base.metadata.create_all` at
startup plus a documented `--reset` command; no Alembic. Document metadata is duplicated between
PostgreSQL (source of truth) and Qdrant payloads by design, and ingestion writes both in one unit
of work.

**Consequence.** No migration ceremony during a 4-week build, and the reset path is the honest
one for a demo with synthetic data. Cost: no upgrade path for a populated production database —
acceptable, because there is no production database. The two stores can drift, so re-ingest is
idempotent (deterministic chunk ids) and `documents.source_path` is unique.

---

## ADR-009 — Clause segmentation by structure, with an LLM fallback

**Status:** Accepted — fallback trigger resolved 2026-09-10

**Context.** Contract review needs clause-level units, not fixed-size chunks. Structural
segmentation (headings, numbering) is fast and deterministic but breaks on unconventional
formatting; LLM segmentation is robust but slow and non-deterministic.

**Decision.** Structure-first, matching `1.`, `1.1`, `ARTICLE N`, and `SECTION N` headings. The
LLM fallback triggers when **either** the structural pass yields fewer than 2 clauses **or** any
single structural clause exceeds `SEGMENTATION_MAX_CLAUSE_CHARS` (4000) — the second condition
catches the common failure where one heading matches and the rest of the contract lands in a
single blob. `Clause.segmentation_path` records which path ran, and the eval reports it.

**Consequence.** Most contracts segment deterministically, keeping the eval reproducible. Cost:
two code paths to test, and the contract eval set must include at least one contract that
exercises the fallback or it ships untested (enforced by a check in `eval/run_contract_eval.py`).

---

## ADR-010 — Contract output is decision support, not legal advice

**Status:** Accepted (proposal §3, §15)

**Context.** A clause-level compliance verdict reads like a legal opinion, and a user under time
pressure may treat it as one. The system is a 7B local model over a synthetic policy corpus.

**Decision.** Every contract-review output carries the `LEGAL_DISCLAIMER` constant — in the UI, in
the API response body, and in the MCP tool result. It is a required field with no default, so a
response cannot be constructed without it, and it is asserted by tests at all three exits.

**Consequence.** The claim being made is honest and visible at every exit point. Cost: three
places to keep in sync; the MCP result is the easy one to forget because no human sees it during
development.

---

## ADR-011 — Verdict semantics, and what happens when no policy is retrieved

**Status:** Accepted — new, 2026-09-10

**Context.** The proposal names four verdicts but does not define them, and does not say what to
return when policy retrieval finds nothing for a clause. The dangerous default is `Compliant`: a
clause that could not be checked would be reported as fine.

**Decision.** Definitions, fixed in `contracts/reviewer.Verdict`:

| Verdict | Means |
|---|---|
| `Compliant` | The clause is consistent with the cited policy. |
| `Deviates` | The clause contradicts a specific requirement in the cited policy. |
| `Missing` | The cited policy requires a term the clause omits. |
| `Needs Legal Review` | Policy is silent, ambiguous, or retrieval was insufficient to judge. |

**A clause whose policy retrieval returns insufficient evidence is always `Needs Legal Review`,
never `Compliant` and never `Missing`.** `Missing` is a positive finding about a policy we did
retrieve; it requires a citation. A `Compliant` verdict likewise requires a citation, and the
reviewer rejects one without it.

**Consequence.** The system fails toward human review, which is the correct direction for a
decision-support tool. Cost: on a thin policy corpus, `Needs Legal Review` may dominate the
confusion matrix — that is informative about corpus coverage, and the eval reports the rate rather
than suppressing it.

---

## ADR-012 — Citations are (document_id, page); retrieval k and reporting k are separate

**Status:** Accepted — new, 2026-09-10

**Context.** The ground-truth set labels expected sources as `(document_id, page)` (proposal §6),
so page provenance must survive parsing and chunking. Separately, the number of chunks sent to
the LLM and the *k* used for `precision@k` reporting were conflated in the scaffold.

**Decision.** A citation is `(document_id, document_title, page, chunk_id)`. A chunk spanning a
page boundary is attributed to the page where it **starts**. DOCX has no fixed pages, so the
parser emits one `ParsedPage` per top-level section and records that mapping rule in its
docstring.

`RETRIEVAL_TOP_K` (context size, default 5) and `EVAL_REPORT_K` (metric reporting, fixed at 5)
are separate settings. Retrieval metrics are computed over the **retrieved list**, not over the
context actually sent to the LLM, so a sweep of `RETRIEVAL_TOP_K` does not silently redefine
`precision@5`.

**Consequence.** Metrics stay comparable across sweeps. Cost: two settings that are equal by
default and therefore easy to assume are one; both appear in the provenance block.

---

## ADR-013 — The planted prompt-injection document stays in the corpus permanently

**Status:** Accepted — new, 2026-09-10

**Context.** Testing prompt-injection resistance through real retrieval requires a payload inside
an ingested document. It could be ingested only for the red-team run, or left in the corpus
permanently.

**Decision.** Permanently, tagged at `confidential` in a single department, and listed in the
manifest as `injection_test: true`.

**Consequence.** The strongest form of the test: the payload is present in every run, including
the ones that produce the headline retrieval numbers, so it cannot pass by being absent. Cost: it
is one of the 10–15 corpus documents and slightly pollutes corpus statistics; the manifest flag
lets the eval report corpus size with and without it.

---

## Open questions

None blocking. Log new ones here and promote to an ADR when decided.

- Reranker model for Config B (hybrid + rerank). Only needed if Config B survives the cut list in
  `docs/PLAN.md`; the config plumbing (`RERANKER_MODEL`, `RETRIEVAL_MODE=hybrid_rerank`) is in
  place and the engine raises `NotImplementedError` on that path until a model is chosen.
