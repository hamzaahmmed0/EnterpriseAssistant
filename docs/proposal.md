# Project Proposal — Enterprise Knowledge Assistant

**Access-Controlled Document Q&A and Automated Contract Compliance Review**

This is the authoritative spec. `docs/PLAN.md` is the execution plan derived from it,
`docs/DECISIONS.md` records what has been decided (and what is still open), and
`docs/EVALUATION.md` is the measurement protocol.

---

## 1. Project overview

**Problem statement.** Employees need one reliable place to ask questions about internal company
documents and get trustworthy, access-controlled answers — and to have contracts checked against
company policy before signing, without waiting on legal or manually cross-referencing lengthy
policy documents. Existing solutions fall short in three ways:

- General-purpose AI chatbots have no concept of document-level access control, so any employee
  could unintentionally retrieve information from documents they are not authorized to see.
- Most RAG systems retrieve once and generate an answer regardless of whether the retrieved
  evidence is sufficient, leading to hallucinated or ungrounded answers.
- Even well-built RAG systems are locked inside their own chat window, disconnected from the tools
  employees already use, and cannot proactively check a document (such as a contract) against
  company knowledge.

**Background.** Organizations accumulate large volumes of internal documents — policies, SOPs,
contracts, handbooks — scattered across drives and folders. Employees waste time searching them
manually, and legal/compliance teams are routinely asked to review contracts against internal
policy, a slow and error-prone process.

**Why it matters.** The two failure modes that matter most for internal AI adoption are trust and
security: an assistant that gives ungrounded answers erodes confidence, and one with no access
boundary is a security liability. Solving both — and extending the same trusted core to a real
business workflow — demonstrates a credible foundation for an internal enterprise tool.

**Proposed solution.** A single underlying retrieval engine — permission-aware and self-correcting
— powering two user-facing capabilities:

1. **Ask** — chat over company documents, answers scoped strictly to what the logged-in user is
   authorized to see, every answer backed by a citation to its source document.
2. **Check** — contract upload, clause-level segmentation, and a clause-by-clause compliance
   verdict against internal policy, cited to the specific policy clause checked against.

**Target users.** Employees across departments (Finance, HR, Legal, Engineering) needing quick,
trustworthy answers from internal documents; employees and managers needing a first-pass compliance
check on a contract before escalating to legal.

## 2. Objectives

- Implement RAG over a domain-specific internal document corpus.
- Enforce document-level access control inside the retrieval layer itself, not as a post-hoc filter.
- Design and calibrate an adaptive retrieval loop that detects weak evidence and self-corrects
  before generating.
- Extend the same retrieval core to a structurally different task — clause-level contract
  compliance checking — to demonstrate reusability.
- Expose the backend through MCP as an implementation-level detail, so the engine is not locked to
  a single front end.
- Empirically evaluate against a fixed single-shot RAG baseline using a labeled ground-truth
  dataset, rather than anecdotal claims.

## 3. Scope

**In scope**

- Synthetic company knowledge base (2–3 departments, 10–20 documents: policies, SOPs, handbooks).
- Ingestion pipeline: parsing, chunking, embedding, access-level tagging.
- Permission-aware vector retrieval with pre-filtering at the search layer.
- Adaptive retrieval loop with a calibrated confidence threshold and bounded retry/reformulation.
- Chat-based **Ask** interface with source citations.
- **Check** contract review: clause-level chunking, per-clause policy retrieval, and a
  Compliant / Deviates / Missing / Needs Legal Review verdict with citations.
- Basic authentication with 3–4 demo user roles/departments.
- MCP server exposing `search_documents` and `submit_contract_for_review`.
- Comparative empirical evaluation: fixed vs. adaptive retrieval, plus a contract-review eval set.

**Out of scope**

- Real-time integration with live enterprise systems (actual Google Drive / SharePoint).
- Fine-tuning a custom LLM.
- Multi-contract comparison, analytics dashboards, human-in-the-loop review queue.
- Auto-rewriting deviating contract clauses.
- Legal-grade compliance guarantees — the system is explicitly decision support.

**Expected limitations**

- The knowledge base is synthetic, not a real corpus (data-privacy constraint).
- The adaptive threshold is calibrated on a small labeled set (30–50 Q&A pairs, trimmed to 20–30
  for timeline), limiting statistical confidence.
- Clause-level segmentation is a known hard problem; performance may vary across contract formats.

## 4. AI/ML components

- Document preprocessing: PDF/DOCX parsing, cleaning, chunking.
- Embeddings: dense vectors (BGE-small or Nomic-embed-text) for semantic retrieval.
- RAG: the core mechanism for both Ask and Check.
- Prompt engineering: strict "answer only from retrieved context, cite source" prompting.
- Adaptive retrieval / agentic control flow: a LangGraph node that scores retrieved evidence and
  triggers a reformulate-and-retry loop when evidence is insufficient (bounded to 2–3 attempts).
- Tool/function calling: MCP tools (`search_documents`, `get_document_metadata`,
  `submit_contract_for_review`) that carry caller identity through to the access-control layer.
- Evaluation: precision@5, recall@5, MRR, groundedness/faithfulness, contract-verdict accuracy.
- Guardrails: access-control pre-filtering, citation-required generation, explicit
  "suggestion, not legal advice" labeling.

Fine-tuning is not required; the focus is retrieval quality, access control, and workflow
integration rather than model adaptation.

## 5. Proposed architecture

```
User -> Frontend (Next.js) -> Backend/API (FastAPI) -> Retrieval Engine -> Vector DB (Qdrant)
                                                    -> LLM (Qwen/Ollama) -> Response
                                    |
                                    +-> Contract Reviewer (reuses Retrieval Engine) -> Clause Verdicts
                                    |
                                    +-> MCP Server (exposes same tools to external clients)
```

- **Frontend:** Next.js/React — chat (Ask), contract upload (Check), citation display, login/role
  indicator.
- **Backend/API:** FastAPI — authentication, routing (`/ask`, `/check-contract`, `/documents`),
  orchestration between retrieval engine and contract reviewer.
- **AI/Agent layer:** LangChain + LangGraph — permission-filtered retrieval and the adaptive loop.
- **Vector DB:** Qdrant, storing chunk embeddings alongside `department` / `access_level` metadata
  used for native pre-filtering.
- **Relational DB:** PostgreSQL — users, roles, document metadata, conversation history, contract
  review records.
- **Protocol layer:** an MCP server exposing retrieval and contract-review tools to any
  MCP-compatible client, in addition to the REST API.
- **Authentication:** role/department-based demo auth (3–4 hardcoded users).
- **Deployment:** Dockerized services deployable to a single cloud VM.

**Key architectural decision.** Access control is enforced inside the vector search filter (native
Qdrant pre-filtering keyed to the authenticated caller), not applied after retrieval. The same
filter is enforced identically whether the request arrives via the chat UI or an MCP tool call —
MCP is a new transport, not a new trust boundary.

## 6. Dataset / knowledge sources

- **Sources:** synthetic internal knowledge base — policies, SOPs, handbooks across 2–3 mock
  departments (HR, Finance, Engineering).
- **Format:** PDF and DOCX.
- **Size:** 10–20 documents for the knowledge base; 10–15 synthetic contracts (3–6 clauses each)
  for contract-review evaluation.
- **Cleaning:** removal of headers/footers/PDF extraction artifacts; whitespace and encoding
  normalization.
- **Preprocessing:** fixed-size chunking with overlap for general documents; clause-level
  segmentation (section headers/numbering, with an LLM-based classification fallback) for contracts.
- **Ground truth:** 30–50 Q&A pairs (direct, paraphrased, multi-hop, exact-identifier, negative,
  cross-document), each labeled with expected source document and page. A separate labeled set for
  Check, where each clause's compliant/deviating/missing status is known in advance.
- **Embedding strategy:** dense embeddings via BGE-small or Nomic-embed-text, stored in Qdrant with
  access-control metadata.

## 7. Technology stack

| Layer | Technology |
|---|---|
| Frontend | Next.js / React |
| Backend | FastAPI |
| Language | Python |
| LLM | Qwen (via Ollama) |
| AI framework | LangChain + LangGraph |
| Embeddings | BGE-small / Nomic-embed-text |
| Vector DB | Qdrant |
| Relational DB | PostgreSQL |
| Tool protocol | Model Context Protocol (MCP) |
| Deployment | Docker + cloud platform |
| Version control | Git + GitHub |

## 8. AI/ML workflow

**Ask (RAG pipeline)**

```
Documents -> Parsing -> Cleaning -> Chunking -> Embedding -> Qdrant (tagged with access_level)
  -> Query -> Permission-filtered retrieval -> Evidence scoring
  -> [if below threshold: reformulate and retry, capped at 2-3 attempts]
  -> LLM generation (context-only, citation-required) -> Answer with source citation
```

**Check (contract review pipeline)**

```
Contract upload -> Parsing -> Clause segmentation (headers/numbering, LLM fallback)
  -> Per-clause permission-filtered retrieval against policy corpus
  -> Clause-vs-policy comparison (LLM)
  -> Verdict: Compliant / Deviates / Missing / Needs Legal Review, with citation
  -> Clause-by-clause report
```

**Tool-call flow (MCP)**

```
External client -> MCP tool call (carries user identity) -> Access-control check
  -> Retrieval/Contract pipeline -> Structured result
```

## 9. Evaluation metrics

**Retrieval / RAG:** precision@5, recall@5, MRR; manually-graded answer accuracy against the
ground-truth Q&A set; groundedness/faithfulness; answer relevance; response latency.

**Access control:** pass/fail rate on an adversarial test suite (10–15 queries including
paraphrased attempts and a prompt-injection payload), run once through the chat UI and once through
the MCP tool interface, to confirm the boundary holds across transports.

**Contract review:** clause-classification accuracy against the labeled contract set; citation
accuracy (was the correct policy document/section cited); qualitative rubric for explanation
quality.

**Comparative study:** fixed single-shot retrieval vs. fixed hybrid+reranker retrieval vs. adaptive
retrieval, compared on the same Q&A set across all metrics above, including the latency cost of the
adaptive loop.

## 10. Functional requirements

- User can log in and be identified by department/role.
- User can ask natural-language questions about company documents via chat.
- System retrieves only documents the user is authorized to access.
- System generates answers grounded in retrieved context, with source citations.
- User can upload a contract for compliance review.
- System returns a clause-by-clause verdict report with citations to relevant policy.
- External MCP clients can call `search_documents` and `submit_contract_for_review` with the same
  access-control guarantees as the chat UI.
- Admin/demo user can view which documents exist and their access-level tags.

## 11. Non-functional requirements

- **Performance:** answer returned within an acceptable latency window (target defined during
  evaluation, accounting for adaptive retries).
- **Scalability:** new documents/departments can be added without redesign.
- **Security:** access control enforced at the retrieval layer, not the presentation layer; no
  unauthorized content enters the LLM context window.
- **Reliability:** the adaptive loop has a defined "insufficient evidence" fallback rather than
  looping indefinitely or hallucinating.
- **Data privacy:** synthetic data only.
- **Maintainability:** clear separation between ingestion, retrieval, and generation layers.

## 12. UI / UX

- **Login:** demo login with role/department selection.
- **Ask:** message input, streamed answers, inline source citations, department indicator.
- **Check:** file upload, processing status, clause-by-clause verdict report with colour-coded
  status and citations.
- **Document list:** documents the logged-in user is authorized to see.
- **(Stretch) Admin panel:** ingested documents and their access tags.

## 13. API design

```
POST /auth/login
GET  /documents
POST /ask
POST /check-contract
GET  /conversation/{id}
```

MCP tools mirror the core endpoints (`search_documents`, `submit_contract_for_review`,
`get_document_metadata`), each requiring the caller's authenticated identity so access control is
enforced identically regardless of entry point.

## 14. Database design

**PostgreSQL**

- `users` (id, name, department, role)
- `documents` (id, title, department, access_level, source_path)
- `conversations` (id, user_id, created_at)
- `messages` (id, conversation_id, role, content, citations)
- `contract_reviews` (id, user_id, contract_name, status, created_at)
- `clause_verdicts` (id, contract_review_id, clause_text, verdict, cited_policy_doc, explanation)

**Qdrant**

- `documents_collection` — chunk embeddings with metadata: document_id, department, access_level,
  page
- `policy_collection` — policy chunk embeddings used specifically for contract-clause comparison

## 15. Security

- Role/department-based authentication for demo users.
- Authorization enforced via native vector-search pre-filtering keyed to the authenticated caller.
- Input validation on file uploads (type/size checks).
- Prompt-injection resistance testing, including a payload embedded in a test document.
- Access control validated identically across the chat UI and the MCP tool interface.
- Explicit labeling of contract-review output as a suggestion, not legal advice.

## 16. Testing

- Unit: chunking, embedding, retrieval-filter functions.
- API: `/ask`, `/check-contract`, `/documents`.
- Integration: end-to-end from document upload through retrieval to generated answer.
- RAG evaluation against the labeled Q&A ground-truth set.
- Access control: 10–15 adversarial queries as an unauthorized user, via both chat UI and MCP.
- Contract review against the labeled synthetic contract set.
- Edge cases: empty/ambiguous queries, malformed uploads, documents with no matching policy.
- Failure handling: defined "insufficient evidence" fallback after the retry cap.

## 17. Deployment

```
GitHub -> Docker build -> Backend (FastAPI) + Qdrant + PostgreSQL -> Frontend (Next.js)
  -> Cloud VM / container platform
```

Basic CI (build/test on push) if the timeline allows; full CI/CD is a stretch goal.

## 18. Monitoring & logging

- API request/response logs.
- Error logs for ingestion, retrieval, generation failures.
- Retrieval-quality logs (evidence score per query, retry count).
- Access-control decision logs (filter applied, allow/deny outcome) for auditability.
- Latency logs per pipeline stage (retrieval, scoring, generation).
- Token usage per query.

## 19. Project timeline

**Week 1 — Foundation.** Goal: data ready, baseline RAG working end-to-end.

| Days | Work |
|---|---|
| 1–2 | Synthetic company setup (2–3 departments, 10–15 documents), ground-truth Q&A set (20–30 pairs, trimmed from 30–50) |
| 3–4 | Ingestion pipeline: parsing, chunking, embeddings, Qdrant setup |
| 5–7 | Baseline fixed-retrieval RAG end-to-end (retrieval + generation with citations) |

Deliverable: working baseline RAG, ground-truth set locked.

**Week 2 — Access control + adaptive retrieval.** Goal: the two core research contributions, done
and evaluated.

| Days | Work |
|---|---|
| 1–2 | Permission-aware retrieval (native Qdrant pre-filtering) |
| 3 | Access-control red-team suite (8–10 adversarial queries) + pass/fail results |
| 4–5 | Adaptive retrieval loop (LangGraph): evidence scoring + reformulate-retry |
| 6–7 | Threshold calibration against ground-truth set, document the method |

Deliverable: permission-aware + adaptive retrieval both working and evaluated against baseline —
the core empirical result; must not slip.

**Week 3 — Product surface + contract review.** Goal: both features demoable.

| Days | Work |
|---|---|
| 1–2 | Frontend Ask interface (chat, citations) + basic auth/roles (3–4 demo users) |
| 3–4 | Contract Reviewer: clause segmentation + per-clause retrieval (reuse Week 2 pipeline) |
| 5–6 | Verdict generation + Check UI |
| 7 | Small contract eval set (5–8 synthetic contracts, trimmed from 10–15) |

Deliverable: Ask and Check working end-to-end with live access control.

**Week 4 — Evaluation, polish, delivery.**

| Days | Work |
|---|---|
| 1–2 | Full comparative experiment; contract-review accuracy table |
| 3 | Bug fixing, edge-case handling |
| 4 | Deployment (Docker, single cloud instance) |
| 5–7 | Final report, results write-up, demo rehearsal |

Deliverable: deployed system, two results tables, final report and demo ready.

## 20. Expected outcomes

- A working Ask + Check web application with a demoable UI.
- A permission-aware, adaptive RAG pipeline empirically evaluated against a fixed-retrieval
  baseline.
- An MCP server exposing the same capabilities as standard tools.
- A clause-level contract compliance reviewer with its own labeled eval set and results table.
- A documented, calibrated adaptive-retrieval threshold with a stated calibration method.
- A full evaluation report covering retrieval metrics, access-control red-team results (both
  transports), and contract-review accuracy.
- Complete technical documentation and a live demo showing role-based access control in action.

## 21. Future enhancements

- Auto-rewrite suggestions for deviating clauses.
- Multi-contract comparison and analytics dashboard.
- Human-in-the-loop review queue for flagged clauses.
- Additional MCP primitives (resources, prompt templates).
- Integration with real enterprise document stores.
- Multilingual document support.
- CI/CD pipeline for automated testing and deployment.
