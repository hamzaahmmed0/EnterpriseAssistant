# Enterprise Knowledge Assistant

Access-controlled document Q&A and automated contract compliance review.

**Status: scaffolding.** Every source file in this repo is a stub (signature + docstring +
`NotImplementedError`). Nothing runs yet. See [docs/PLAN.md](docs/PLAN.md) for the build order.

---

## The problem

Employees need one trustworthy place to ask questions about internal documents, and a fast
first-pass compliance check on contracts before they reach legal. General chat assistants have no
concept of document-level access control, so any employee can surface content they are not cleared
to see. Ordinary RAG systems retrieve once and generate regardless of whether the retrieved
evidence actually supports an answer, so they hallucinate rather than admit ignorance.

## The solution

One permission-aware, self-correcting retrieval engine — access control is applied as a *pre-filter
inside the vector search*, and retrieved evidence is scored before generation with a bounded
reformulate-and-retry loop — exposed through two surfaces: **Ask** (cited chat Q&A scoped to the
caller's department and access level) and **Check** (clause-level contract review with a
Compliant / Deviates / Missing / Needs Legal Review verdict per clause, cited to policy). The same
engine is reachable over REST and over MCP, with identical enforcement on both paths.

---

## Architecture

```
                        +------------------------------+
                        |  Frontend (Next.js/React)    |
                        |  Ask . Check . Documents     |
                        +---------------+--------------+
                                        | server-side fetch only
                                        v
                        +------------------------------+      +--------------------+
  MCP client ---------->|  Backend API (FastAPI)       |<---->| PostgreSQL         |
  (search_documents,    |  /auth /documents /ask       |      | users, documents,  |
   submit_contract_...) |  /check-contract /conv/{id}  |      | messages, reviews  |
                        +---------------+--------------+      +--------------------+
                                        | Identity(department, access_level)
                                        v
        +------------------------------------------------------------+
        |  Retrieval Engine                                          |
        |   +------------------------------------------------+       |
        |   | access_filter: Identity -> Qdrant Filter        |       |
        |   +----------------------+-------------------------+       |
        |                          v                                 |
        |   retrieve (PRE-filtered)                                  |
        |     -> score evidence                                      |
        |         -> below threshold: reformulate, retry  (LangGraph,|
        |            bounded by ADAPTIVE_MAX_ATTEMPTS)     hard cap)  |
        |         -> ok: generate                                    |
        |         -> exhausted: "insufficient evidence"              |
        +------------+----------------------------------+------------+
                     v                                  v
        +---------------------+            +---------------------------+
        | Qdrant              |            | LLM (Qwen via Ollama)     |
        | documents_collection|            | context-only,             |
        | policy_collection   |            | citation-required         |
        +---------------------+            +---------------------------+
                     ^
                     | reuses the engine, no bypass
        +------------+--------+
        | Contract Reviewer   |  segment -> per-clause retrieve -> verdict
        +---------------------+
```

Two invariants the diagram encodes, and the reason this project exists:

1. The access filter sits **before** the vector search, not after it. Unauthorized chunks never
   reach the LLM context window.
2. The MCP server is another transport into the same box. It is not a trust boundary and has no
   private code path.

---

## Tech stack

| Layer | Choice | Notes |
|---|---|---|
| Frontend | Next.js / React (TypeScript, strict) | server-side calls to the backend only |
| Backend | FastAPI (Python) | auth, routing, orchestration |
| Agent layer | LangChain + LangGraph | evidence scoring + bounded retry loop |
| LLM | Qwen via Ollama (local) | exact tag undecided — ADR-005 |
| Embeddings | BGE-small *or* Nomic-embed-text | undecided — ADR-005 |
| Vector DB | Qdrant | native payload pre-filtering |
| Relational DB | PostgreSQL | users, documents, conversations, reviews |
| Tool protocol | MCP | `search_documents`, `get_document_metadata`, `submit_contract_for_review` |
| Deploy | Docker Compose to a single cloud VM | Sprint 4 |

---

## Repo layout

```
backend/
  app/
    api/            REST surface: routes, request/response schemas, auth dependency
    ingestion/      parse -> clean -> chunk -> embed -> upsert into Qdrant
    retrieval/      access filter, Qdrant wrapper, evidence scoring, LangGraph adaptive loop
    generation/     prompts, Ollama client, context-only citation-required answer assembly
    contracts/      clause segmentation + per-clause verdict generation
    mcp/            MCP server exposing the same tools over a different transport
  tests/            unit tests for chunking, the permission filter, clause segmentation
frontend/
  app/              Next.js routes: login, /ask, /check, /documents
  components/       chat, citations, upload, verdict table
  lib/              typed backend client, shared types, demo session handling
eval/
  datasets/         ground-truth Q&A set, labeled contracts, adversarial queries
  results/          run outputs; every file records the config that produced it
docs/               proposal (spec), execution plan, ADR log, evaluation protocol
data/               synthetic corpus and uploaded contracts — contents never committed
```

Directory-by-directory:

| Path | What lives here |
|---|---|
| `backend/app/api` | HTTP endpoints and the dependency that turns a session token into an `Identity` |
| `backend/app/ingestion` | Document parsing, cleaning, chunking, embedding, and Qdrant upsert |
| `backend/app/retrieval` | The engine: permission pre-filter, vector search, evidence scoring, adaptive loop |
| `backend/app/generation` | Prompt templates, LLM client, grounded answer + insufficient-evidence fallback |
| `backend/app/contracts` | Clause segmentation and clause-vs-policy verdicts |
| `backend/app/mcp` | MCP tool definitions and server wiring |
| `backend/tests` | Tests for the three places silent breakage is most expensive |
| `frontend/app` | Next.js App Router pages |
| `frontend/components` | Presentational React components |
| `frontend/lib` | Server-side API client, shared TS types, session helpers |
| `eval/` | Metric implementations and the three comparison harnesses |
| `docs/` | `proposal.md`, `PLAN.md`, `DECISIONS.md`, `EVALUATION.md` |

---

## Local setup

Prerequisites: Docker + Docker Compose, Python 3.11+, Node 20+, Ollama (host or in-compose).

```bash
cp .env.example .env
```

1. **Fill `.env`.** Several values are open questions (chunk size, evidence threshold, embedding
   model) — see `docs/DECISIONS.md` before guessing.
2. TODO: start infrastructure (`docker compose up -d qdrant postgres`) and document the readiness
   check for each service.
3. TODO: pull the LLM and embedding models via Ollama; record the exact tags in `docs/DECISIONS.md`.
4. TODO: backend dependency install command — decide uv vs pip + venv (see `backend/pyproject.toml`).
5. TODO: database bootstrap command — decide Alembic vs `create_all` (ADR-008).
6. TODO: Qdrant collection creation command; it must assert `EMBEDDING_DIM` matches the model.
7. TODO: ingestion command to load `data/corpus/` into Qdrant.
8. TODO: run the backend (`uvicorn app.main:app --reload`) and the frontend (`npm run dev`).
9. TODO: MCP server launch command plus the client config snippet to paste into an MCP client.

## Running the evaluation

TODO once Sprint 1 lands — see [docs/EVALUATION.md](docs/EVALUATION.md) for the protocol, dataset
schemas, and the (currently empty) results tables.

---

## Disclaimer

Contract review output is **decision support, not legal advice**. This labeling is required in the
UI, in the API response, and in the MCP tool result.
