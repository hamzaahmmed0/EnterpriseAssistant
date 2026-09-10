# Enterprise Knowledge Assistant

Access-controlled document Q&A and automated contract compliance review.

**Status: implemented, not yet measured.** Every module is written and 132 backend tests pass; the
frontend builds. What does *not* exist yet is the data: the synthetic corpus and the three
labelled eval sets are authored by the team (`docs/PLAN.md` tasks 1.1, 1.2, 2.4, 3.9). Until they
exist, nothing can be ingested and the results tables in `docs/EVALUATION.md` stay empty.

---

## The problem

Employees need one trustworthy place to ask questions about internal documents, and a fast
first-pass compliance check on contracts before they reach legal. General chat assistants have no
concept of document-level access control, so any employee can surface content they are not cleared
to see. Ordinary RAG systems retrieve once and generate regardless of whether the retrieved
evidence actually supports an answer, so they hallucinate rather than admit ignorance.

## The solution

One permission-aware, self-correcting retrieval engine — access control is applied as a *pre-filter
inside the vector search*, and retrieved evidence is judged before generation with a bounded
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
        |     -> judge evidence (LLM, temperature 0, cached)         |
        |         -> below threshold: reformulate, retry  (LangGraph,|
        |            bounded by ADAPTIVE_MAX_ATTEMPTS)     hard cap)  |
        |         -> ok: generate                                    |
        |         -> exhausted: "insufficient evidence"              |
        +------------+----------------------------------+------------+
                     v                                  v
        +---------------------+            +---------------------------+
        | Qdrant              |            | Ollama                    |
        | documents_collection|            | qwen2.5:7b-instruct (gen) |
        | policy_collection   |            | nomic-embed-text (embed)  |
        +---------------------+            +---------------------------+
                     ^
                     | reuses the engine, no bypass
        +------------+--------+
        | Contract Reviewer   |  segment -> per-clause retrieve -> verdict
        +---------------------+
```

Two invariants the diagram encodes, and the reason this project exists:

1. The access filter sits **before** the vector search, not after it. Unauthorized chunks never
   reach the LLM context window. `backend/tests/test_vector_store_guard.py` fails if any code path
   can reach the store without one.
2. The MCP server is another transport into the same box. It is not a trust boundary and has no
   private code path.

---

## Tech stack

| Layer | Choice | Notes |
|---|---|---|
| Frontend | Next.js 15 / React 19 (TypeScript, strict) | server actions only; no client-side backend calls |
| Backend | FastAPI (Python 3.11+) | auth, routing, orchestration |
| Agent layer | LangGraph | evidence judging + bounded retry loop |
| LLM | `qwen2.5:7b-instruct` via Ollama | temperature 0 for replayable runs — ADR-005 |
| Embeddings | `nomic-embed-text` via Ollama, 768d | one model runtime for both jobs — ADR-005 |
| Vector DB | Qdrant | native payload pre-filtering, indexed on the tag fields |
| Relational DB | PostgreSQL | `create_all`, no Alembic — ADR-008 |
| Tool protocol | MCP (`mcp` Python SDK) | `search_documents`, `get_document_metadata`, `submit_contract_for_review` |
| Deploy | Docker Compose to a single VM | see `docker-compose.yml` |

Access model (ADR-006): `access_level` is ordinal — `public < internal < confidential` — and
`department` is a hard partition, with the reserved department `all` for org-wide documents.

---

## Repo layout

```
backend/
  app/
    api/            REST surface: routes, request/response schemas, auth dependency
    ingestion/      parse -> clean -> chunk -> embed -> upsert into Qdrant
    retrieval/      access filter, Qdrant wrapper, evidence judge, LangGraph adaptive loop
    generation/     prompts, Ollama client, context-only citation-required answer assembly
    contracts/      clause segmentation + per-clause verdict generation
    mcp/            MCP server exposing the same tools over a different transport
  tests/            132 tests; no service required to run them
frontend/
  app/              Next.js routes: login, /ask, /check, /documents, plus server actions
  components/       chat, citations, upload, verdict table, role badge
  lib/              server-only API client, shared TS types, session cookies
eval/
  datasets/         ground-truth Q&A set, labelled contracts, adversarial queries
  results/          run outputs; every file records the config that produced it
docs/               proposal (spec), execution plan, team split, ADR log, evaluation protocol
data/               synthetic corpus and uploaded contracts — contents never committed
```

| Path | What lives here |
|---|---|
| `backend/app/api` | HTTP endpoints and the dependency that turns a session token into an `Identity` |
| `backend/app/ingestion` | Document parsing, cleaning, chunking, embedding, and Qdrant upsert |
| `backend/app/retrieval` | The engine: permission pre-filter, vector search, evidence judge, adaptive loop |
| `backend/app/generation` | Prompt templates, LLM client, grounded answer + insufficient-evidence fallback |
| `backend/app/contracts` | Clause segmentation and clause-vs-policy verdicts |
| `backend/app/mcp` | MCP tool definitions and server wiring |
| `backend/tests` | Chunking, the permission filter, the adaptive loop, contracts, auth coverage, metrics |
| `frontend/app` | Next.js App Router pages and server actions |
| `frontend/components` | React components |
| `frontend/lib` | `server-only` API client, shared TS types, session helpers |
| `eval/` | Metric implementations and the three comparison harnesses |
| `docs/` | `proposal.md`, `PLAN.md`, `TEAM.md`, `DECISIONS.md`, `EVALUATION.md` |

---

## Local setup

Prerequisites: Docker + Docker Compose, Python 3.11+, Node 20+.

### 1. Configure

```bash
cp .env.example .env
```

Then set `AUTH_SECRET` in `.env` to a real value:

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

Every other value has a working default from `docs/DECISIONS.md`. The ones worth sweeping later
are `CHUNK_SIZE_TOKENS`, `EVIDENCE_THRESHOLD`, `RETRIEVAL_TOP_K`, and `ADAPTIVE_MAX_ATTEMPTS`.

### 2. Start infrastructure and pull the models

```bash
docker compose up -d qdrant postgres ollama
```

```bash
docker compose run --rm ollama-pull
```

The pull is ~5 GB and happens once. Skipping it means the first query downloads the model while a
user waits, which also ruins that run's latency numbers.

### 3. Install the backend

```bash
cd backend && python -m venv .venv && ./.venv/Scripts/python.exe -m pip install -r requirements.txt -r requirements-dev.txt
```

On macOS/Linux the interpreter is `.venv/bin/python` instead.

### 4. Run the tests (no services needed)

```bash
cd backend && ./.venv/Scripts/python.exe -m pytest -q
```

### 5. Author the corpus, then ingest

Put documents under `data/corpus/` and write `data/corpus/manifest.json`. Access tags live in the
manifest and nowhere else — never inferred from a filename:

```json
[
  {
    "document_id": "hr-leave-policy-v3",
    "title": "Annual Leave Policy",
    "path": "hr/leave-policy-v3.pdf",
    "department": "hr",
    "access_level": "internal",
    "collection": "documents",
    "injection_test": false
  }
]
```

`collection` is `documents`, `policy`, or `both`. Contract review only searches the policy
collection, so procurement and compliance policies need `policy` or `both`.

Validate before writing anything:

```bash
cd backend && ./.venv/Scripts/python.exe -m app.ingestion.pipeline --manifest ../data/corpus/manifest.json --dry-run
```

Then ingest for real:

```bash
cd backend && ./.venv/Scripts/python.exe -m app.ingestion.pipeline --manifest ../data/corpus/manifest.json
```

Ingestion refuses to write an untagged chunk and audits both collections afterwards, failing the
run if any point lacks a department or access level.

### 6. Run the backend

```bash
cd backend && ./.venv/Scripts/python.exe -m uvicorn app.main:app --reload
```

`GET /health` reports whether PostgreSQL, Qdrant, and Ollama are each reachable.

### 7. Run the frontend

```bash
cd frontend && npm install && npm run dev
```

Open http://localhost:3000. Demo password for every account is `demo1234`
(`backend/demo_users.json`). Sign in as `hr_generalist` and then as `eng_ic`, ask the same
question, and compare — that contrast is the access-control demo.

### 8. Run the MCP server

```bash
cd backend && ./.venv/Scripts/python.exe -m app.mcp.server
```

Client config (stdio):

```json
{
  "mcpServers": {
    "enterprise-assistant": {
      "command": "backend/.venv/Scripts/python.exe",
      "args": ["-m", "app.mcp.server"],
      "cwd": "backend"
    }
  }
}
```

Every tool takes a `token` from `POST /auth/login`. None accepts a department or access level —
a client-supplied access level would be privilege escalation by design (ADR-002).

### Everything at once

```bash
docker compose up -d
```

---

## Running the evaluation

The three harnesses are runnable now; they need the frozen datasets described in
`docs/EVALUATION.md` section 1. Each validates its dataset before touching a service:

```bash
python -m eval.run_retrieval_eval --config A --dry-run
```

```bash
python -m eval.run_retrieval_eval --config A          # baseline, fixed retrieval
```

```bash
python -m eval.run_retrieval_eval --config C          # adaptive
```

```bash
python -m eval.run_access_control_eval --transport both
```

```bash
python -m eval.run_contract_eval
```

Run these from the repo root with the backend venv active. Each writes a results file to
`eval/results/` carrying a full provenance block — model, embedding, chunk size, threshold,
dataset hash, git commit — and refuses to write one without it. The red-team harness exits
non-zero on any leak, so it can gate a release.

---

## Disclaimer

Contract review output is **decision support, not legal advice**. This labelling is enforced in the
API response schema, the MCP tool result, and the UI, and is asserted by tests at all three exits.
