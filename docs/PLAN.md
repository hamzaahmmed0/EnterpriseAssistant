# Execution Plan

Four sprints, one per week, matching `docs/proposal.md` §19. Each sprint has a goal, scoped tasks,
a deliverable, an entry dependency, and a **done when** criterion that someone else could check
without asking me whether it "works".

**The core contribution is Sprint 2** (permission-aware retrieval + the adaptive loop, each
measured against the Sprint 1 baseline). Everything else exists to make that result presentable.
If time slips, cut from Sprints 3 and 4 — never from Sprint 2.

---

## Critical path

```
synthetic corpus + ground-truth Q&A set (locked)
        |
        v
ingestion -> Qdrant populated with department/access_level payloads
        |
        v
baseline fixed RAG + retrieval metric harness   <-- Sprint 1 ends here
        |
        v
permission pre-filter -> red-team suite passes  \
        |                                        >  Sprint 2: THE RESULT
        v                                       /
adaptive loop -> threshold calibrated -> Config A/B/C comparison run
        |
        v
contract reviewer (reuses the engine)  ----\
        |                                   >  Sprint 3: the demo surface
frontend Ask/Check + demo auth   ----------/
        |
        v
full comparative experiment -> deployment -> report   <-- Sprint 4
```

Anything not on that spine is negotiable.

### Safe to cut, in the order I would cut it

1. Admin panel (proposal calls it a stretch already).
2. Answer streaming in the Ask UI — replace with a spinner and a single final render.
3. Basic CI on push (proposal already conditions this on the timeline).
4. Cloud deployment — demo from `docker compose up` on the laptop; keep the compose file correct.
5. Config B (hybrid + reranker) in the comparison — the headline claim is fixed vs. adaptive.
   Report A vs. C and state that B was descoped, rather than reporting a rushed B.
6. Contract eval set down to 5 contracts (the floor; below this the accuracy table is noise).
7. Conversation history persistence (`/conversation/{id}`) — keep the endpoint, back it with the
   in-request transcript only.

### Not cuttable, at any point

- The permission pre-filter and its red-team suite across **both** transports.
- The bounded adaptive loop and the "insufficient evidence" fallback.
- The frozen ground-truth set and the Config A vs. C comparison table.
- The "decision support, not legal advice" labeling in UI, API, and MCP result.

---

## Sprint 1 — Foundation (Week 1)

**Goal.** Data ready and a baseline single-shot RAG answering end-to-end with citations, plus the
measurement harness that every later sprint reports through.

**Depends on.** Nothing but this scaffold. Decide ADR-003 (chunk size/overlap) and ADR-005
(embedding model) at the *start* of Days 3–4 and record both in `docs/DECISIONS.md` — they block
ingestion and can't be silently defaulted.

**Tasks**

| # | Task | Days |
|---|---|---|
| 1.1 | Author the synthetic corpus: 3 departments (HR, Finance, Engineering), 10–15 PDF/DOCX documents, each with an explicit department + access level. Include at least one document only one role may see, and one containing a prompt-injection payload for the Sprint 2 red-team. | 1–2 |
| 1.2 | Write the ground-truth Q&A set: 20–30 pairs covering direct, paraphrased, multi-hop, exact-identifier, negative, and cross-document question types, each labeled with expected document + page. Schema in `docs/EVALUATION.md`. | 1–2 |
| 1.3 | **Freeze** the ground-truth set: commit it, record the commit hash in `docs/EVALUATION.md`. From here it changes only via the documented correction procedure. | 2 |
| 1.4 | Ingestion: PDF/DOCX parsing + cleaning (headers/footers/whitespace artifacts). | 3 |
| 1.5 | Chunking with overlap, driven entirely by config; unit tests for boundaries, overlap, and empty/short documents. | 3 |
| 1.6 | Embedding wrapper + Qdrant collection creation asserting `EMBEDDING_DIM` matches the model; payload schema includes `document_id`, `department`, `access_level`, `page`. | 4 |
| 1.7 | Ingest the corpus into `documents_collection` and `policy_collection`; assert every point carries a non-null `department` and `access_level` at ingest time (fail the run, don't warn). | 4 |
| 1.8 | Baseline fixed retrieval (top-k, no filter, no retry) + context-only citation-required generation via Ollama. | 5–6 |
| 1.9 | Eval harness: precision@5, recall@5, MRR over the frozen set; results written to `eval/results/` with a full config block (model, embedding, top-k, threshold, retry cap, date, corpus hash). | 6–7 |
| 1.10 | Boundary logging: every retrieval logs evidence score, retry count, applied filter, allow/deny. | 7 |

**Deliverable.** Baseline RAG answering with citations; frozen ground-truth set; one results file
in `eval/results/` for Config A.

**Done when.** `precision@5`, `recall@5`, and `MRR` for Config A (fixed retrieval) are recorded in
`docs/EVALUATION.md` for the full 20–30 question set, produced by a re-runnable script, and the
results file names the exact config that produced them.

---

## Sprint 2 — Access control + adaptive retrieval (Week 2) — **CORE**

**Goal.** Both research contributions implemented and measured. This sprint's output is the
project's empirical claim.

**Depends on.** Sprint 1 done-when satisfied: a populated Qdrant with `department`/`access_level`
payloads on every point, a frozen Q&A set, and a working metric harness. Do not start 2.1 with a
corpus that has partial access tags. Decide ADR-004 (evidence-score definition and retry cap) at
the start of Days 4–5.

**Tasks**

| # | Task | Days |
|---|---|---|
| 2.1 | `Identity` model (user, department, access_level) threaded from the API/auth boundary into every retrieval call — a retrieval call without an identity must be impossible to construct. | 1 |
| 2.2 | `access_filter`: `Identity` → Qdrant `Filter`, passed into `search()` as a native pre-filter. Unit tests asserting the filter object is built correctly per role, plus a test that fails if any code path calls search without a filter. | 1–2 |
| 2.3 | Wire the filter into the engine; keep the engine importable and usable with no web layer. | 2 |
| 2.4 | Red-team suite: 8–10 adversarial queries (direct ask for restricted content, paraphrase, role-play framing, and the prompt-injection payload planted in 1.1), executed as an unauthorized user. | 3 |
| 2.5 | Run the red-team suite through **both** the HTTP path and the MCP path; record pass/fail per query per transport. (Requires a minimal MCP server — build only `search_documents` now.) | 3 |
| 2.6 | Evidence scoring over retrieved chunks (definition per ADR-004), logged per query. | 4 |
| 2.7 | LangGraph adaptive loop: retrieve → score → (reformulate → retry, hard-capped) → generate, with the "insufficient evidence" terminal state as a first-class, tested output. | 4–5 |
| 2.8 | Termination test: a query guaranteed to score below threshold returns the fallback after exactly the configured cap, never more. | 5 |
| 2.9 | Threshold calibration: sweep `EVIDENCE_THRESHOLD` over the frozen set, record the sweep table, pick a value, and write the method down in `docs/EVALUATION.md`. | 6 |
| 2.10 | Comparative run: Config A (fixed) vs. Config C (adaptive) on the frozen set, all retrieval metrics + latency. Config B if 2.1–2.9 finished on time. | 7 |

**Deliverable.** Permission-aware retrieval and the adaptive loop, both working, both measured
against the Sprint 1 baseline, plus a red-team results table covering two transports.

**Done when.** All three hold:
1. Every query in the red-team suite is recorded pass/fail for both the HTTP and MCP transports,
   with zero unauthorized chunks appearing in any logged LLM context.
2. The threshold sweep table is in `docs/EVALUATION.md` with the chosen value and its justification.
3. `precision@5`, `recall@5`, `MRR`, and mean latency are recorded for Config A and Config C on the
   same frozen question set, in one table.

---

## Sprint 3 — Product surface + contract review (Week 3)

**Goal.** Ask and Check demoable end to end, with live access control visible in the UI.

**Depends on.** Sprint 2's engine — the contract reviewer must call it, not reimplement retrieval.
If Sprint 2 is not done, Sprint 3 waits; the fallback is a smaller demo, not an unmeasured core.

**Tasks**

| # | Task | Days |
|---|---|---|
| 3.1 | Demo auth: 3–4 hardcoded users across departments/access levels; login endpoint issuing a session the API turns back into an `Identity`. | 1 |
| 3.2 | Ask UI: chat, inline citations, visible department/role indicator; `/documents` list scoped to the caller. | 1–2 |
| 3.3 | Contract upload endpoint: type + size validation, rejection paths tested. | 3 |
| 3.4 | Clause segmentation: header/numbering-based, with the LLM classification fallback; unit tests over the segmentation cases in the eval contracts. | 3–4 |
| 3.5 | Per-clause retrieval against `policy_collection` through the same permission-filtered engine. | 4 |
| 3.6 | Verdict generation: Compliant / Deviates / Missing / Needs Legal Review, each with a policy citation and a short explanation; "decision support, not legal advice" attached in the API response, the MCP result, and the UI. | 5 |
| 3.7 | Check UI: upload, processing status, colour-coded clause-by-clause report with citations. | 5–6 |
| 3.8 | Add `submit_contract_for_review` and `get_document_metadata` to the MCP server; re-run the relevant red-team queries against the new tools. | 6 |
| 3.9 | Labeled contract eval set: 5–8 synthetic contracts, 3–6 clauses each, each clause labeled with the expected verdict and the expected cited policy document/section. Freeze it. | 7 |
| 3.10 | Persist conversations, messages, contract reviews, and clause verdicts to PostgreSQL. | 7 |

**Deliverable.** Both surfaces working against the live engine, with role-based access visible in
the demo; contract eval set frozen.

**Done when.** Logging in as two different demo users and asking the *same* question returns
demonstrably different (correctly scoped) cited answers; and an uploaded contract from the eval set
returns a verdict plus a policy citation for every clause, with the legal-advice disclaimer present
in the UI, the API response body, and the MCP tool result.

---

## Sprint 4 — Evaluation, polish, delivery (Week 4)

**Goal.** Numbers in hand, system deployed, report written.

**Depends on.** Frozen contract eval set (3.9) and the calibrated threshold (2.9). No result in
this sprint may be produced by a config that isn't recorded alongside it.

**Tasks**

| # | Task | Days |
|---|---|---|
| 4.1 | Full comparative experiment: Configs A / B / C on the frozen Q&A set — retrieval metrics, manually-graded answer accuracy, groundedness, latency. | 1 |
| 4.2 | Contract-review evaluation: clause-classification accuracy + citation accuracy against the frozen contract set; confusion matrix over the four verdicts. | 2 |
| 4.3 | Final red-team re-run on the shipped build, both transports; table refreshed. | 2 |
| 4.4 | Edge cases: empty/ambiguous query, malformed or oversized upload, contract clause with no matching policy, zero-result retrieval. | 3 |
| 4.5 | Docker Compose build details filled in; deploy to a single cloud VM. | 4 |
| 4.6 | Results write-up in `docs/EVALUATION.md`: every table filled, every config recorded, limitations stated honestly. | 5 |
| 4.7 | Final report + demo rehearsal, including the access-control demo (same question, two users) and one deliberate "insufficient evidence" answer. | 5–7 |

**Deliverable.** Deployed system, two results tables (retrieval comparison, contract-review
accuracy) plus the red-team table, final report, rehearsed demo.

**Done when.** Every table in `docs/EVALUATION.md` has real numbers with a provenance block, the
system answers a question from a browser pointed at the deployed instance, and the demo script runs
start to finish without a manual fix-up.

---

## Risks

| Risk | Likelihood | Impact | Mitigation | Cheap fallback |
|---|---|---|---|---|
| Local Qwen inference too slow, evaluation runs take hours | High | High | Batch eval runs; cache retrieval results so generation is the only re-run; pick the smallest Qwen that holds answer quality; run sweeps overnight | Reduce to Config A vs. C on 20 questions and report latency honestly. **Do not** switch to a hosted API mid-experiment — it invalidates comparisons |
| Ground-truth labels turn out to be wrong or ambiguous mid-sprint | Medium | High | Label with document + page during authoring, while the corpus is fresh; two-pass review before freezing | Documented correction procedure: fix the label, note it in `docs/EVALUATION.md`, re-run **all** configs. Never silently patch |
| Adaptive loop shows no improvement over the baseline | Medium | Medium | Calibrate the threshold on a sweep, not a guess; ensure the Q&A set contains genuinely hard paraphrased/multi-hop questions that a single shot should fail | A null result is a valid result. Report it with the sweep table and analyse *why*; do not broaden retrieval to manufacture a win |
| Clause segmentation unreliable across contract formats | Medium | Medium | Author eval contracts with conventional numbering; build the header/numbering path first, LLM fallback second | Restrict the eval set to numbered-clause contracts and state the limitation. Segmentation quality is a stated proposal limitation already |
| Sprint 3 UI work eats Sprint 2 time | Medium | High | Sprint 2 is the freeze zone: no frontend commits until its done-when is met | Ship Ask as a plain form with no styling; Check as a JSON report view |
| Access-control bug: a filter path bypassed somewhere | Low | Critical | Single choke point — one function builds the filter, one function calls search; test that fails if search is called without a filter; red-team both transports | If found late, disable the affected transport rather than shipping a leak |
| Docker/cloud deployment burns Day 4 of Sprint 4 | Medium | Low | Keep compose correct from Sprint 1 onward; deploy is assembly, not design | Demo locally from compose; deployment is not part of the empirical claim |
| Corpus too small for meaningful retrieval metrics | Low | Medium | 10–15 documents with overlapping topics so retrieval is non-trivial | Add 3–5 near-duplicate-topic documents; note the corpus size as a limitation |
| Prompt injection in a corpus document actually succeeds | Low | High | Injection payload planted in Sprint 1 and tested in Sprint 2, not at the end | Report it as a finding with the failing case — it's an honest result, and the pre-filter still holds the access boundary |

---

## Standing rules for every sprint

- Config over constants: thresholds, chunk sizes, top-k, retry caps, model names live in
  `backend/app/config.py`, driven by `.env`. Calibration requires sweeping them.
- Every results file records the config that produced it. Results without provenance are discarded.
- Tests land with the code for chunking, the permission filter, and clause segmentation.
- Open questions go to `docs/DECISIONS.md` as ADRs, not into a magic number in a call site.
