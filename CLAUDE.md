# CLAUDE.md

Instructions for Claude working in this repository.

## What this project is

An access-controlled enterprise document assistant with two surfaces over one retrieval engine:

- **Ask** — chat Q&A over an internal document corpus, answers scoped to the caller's department/access level, every answer cited.
- **Check** — contract upload, clause-level segmentation, per-clause compliance verdict against internal policy, cited.

The engine is permission-aware (filtering happens *inside* vector search) and adaptive (it scores its own evidence and retries before generating). It's exposed both as a REST API and as an MCP server. This is an academic project with a hard 4-week timeline; the deliverable is a working system **plus empirical numbers against a baseline**.

Full spec: `docs/proposal.md`. Execution plan: `docs/PLAN.md`. Read both before non-trivial work.

## Stack

| Layer | Choice |
|---|---|
| Frontend | Next.js / React |
| Backend | FastAPI (Python) |
| Agent layer | LangChain + LangGraph |
| LLM | Qwen via Ollama (local) |
| Embeddings | BGE-small or Nomic-embed-text |
| Vector DB | Qdrant |
| Relational DB | PostgreSQL |
| Tool protocol | MCP |
| Deploy | Docker Compose |

## Non-negotiables

These are the project's contributions. Do not weaken them for convenience.

1. **Access control is a pre-filter, never a post-filter.** Unauthorized chunks must never enter the LLM context window. Every retrieval call takes an authenticated identity and translates it into a Qdrant filter before the search executes. If you find yourself writing `results = [r for r in results if r.allowed]`, stop — that's the bug this project exists to avoid.
2. **MCP is a transport, not a trust boundary.** MCP tool calls go through the exact same access-control path as HTTP requests. No separate code path, no "internal" bypass.
3. **Generation is context-only and citation-required.** If retrieval returns insufficient evidence after the retry cap, the system says so. It does not answer from parametric knowledge. The fallback is a first-class, tested output, not an error case.
4. **The adaptive loop is bounded.** 2–3 attempts, hard cap, always terminates.
5. **Contract output is labeled as decision support, not legal advice.** In the UI, in the API response, in the MCP tool result.
6. **The ground-truth eval set is frozen once locked (end of Week 1).** Do not edit questions or labels to make results look better. If a label is genuinely wrong, fix it, note it in `docs/EVALUATION.md`, and re-run *all* configurations.

## How to work

- **Plan before large changes.** For anything touching more than ~2 files, state the plan and wait for confirmation.
- **Small, reviewable commits.** One logical change each. Conventional-commit prefixes (`feat:`, `fix:`, `test:`, `docs:`, `chore:`).
- **Never commit** `.env`, real credentials, `data/` contents, model weights, or `node_modules`.
- **Don't invent requirements.** If the spec is ambiguous, ask, or log it in `docs/DECISIONS.md` as an open question. Don't silently pick a chunk size, threshold, or schema and bury it in code.
- **Don't scope-creep.** Anything in the proposal's "Out of Scope" or "Future Enhancements" stays out unless I say otherwise. Auto-rewriting clauses, analytics dashboards, real SharePoint integration — no.
- **Tests alongside, not after**, for: chunking, the permission filter, and clause segmentation. These are where silent breakage is most expensive.
- **Config over constants.** Thresholds, chunk sizes, top-k, retry caps, model names all live in config, not hardcoded in call sites — I need to sweep them during calibration.

## Layout conventions

- `backend/` — FastAPI app. Keep `ingestion/`, `retrieval/`, `generation/`, `contracts/`, `mcp/` as separate modules with clear seams. The retrieval engine must be importable and usable without the web layer; the contract reviewer and MCP server both depend on it and neither should reach past it.
- `frontend/` — Next.js. Server-side calls to the backend only; never call Qdrant or the LLM from the browser.
- `eval/` — scripts, datasets, and results. Every result file records the config that produced it (model, embedding, top-k, threshold, retry cap, date). Results are worthless without provenance.
- `docs/` — proposal, plan, decisions, evaluation protocol.

## Code style

- Python: type hints everywhere, `ruff` + `black` defaults, docstrings on public functions.
- TypeScript: strict mode, no `any`.
- Prefer explicit and boring over clever. This code gets read by a grader.
- Log at the boundaries: every retrieval logs its evidence score, retry count, applied filter, and allow/deny outcome. These logs are an evaluation artifact, not debug noise.

## Things that will tempt you and shouldn't

- Adding a "just for testing" flag that skips the permission filter. No.
- Falling back to a hosted API when Ollama is slow. Changes results; note latency instead.
- Broadening retrieval to make an answer appear when the honest output is "insufficient evidence."
- Polishing the UI during Week 2. The empirical result comes first.
