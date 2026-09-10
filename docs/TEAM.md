# Team Split — Three Tracks, Three Owners

`docs/PLAN.md` is the calendar: four weekly sprints, shared by everyone. This document is the
division of labour across it. Each member owns one **track**, and a track spans all four weeks.

Nobody owns a week. Everybody owns a track.

Replace M1 / M2 / M3 with real names before the first commit.

---

## The tracks at a glance

| Track | Owner | Scope | Why it is a unit |
|---|---|---|---|
| **A — Retrieval Core & Evaluation** | M1 | Ingestion, retrieval engine, access filter, adaptive loop, generation, eval harness | This is the critical path and the project empirical claim. It cannot be split further without two people editing the same search call. |
| **B — Product Surface** | M2 | FastAPI API, auth/Identity, PostgreSQL persistence, logging boundary, the whole Next.js frontend | Everything a user touches, plus the plumbing that turns a request into an `Identity`. Independent of A behind one interface. |
| **C — Corpus, Contract Review, MCP & Infra** | M3 | Synthetic corpus, all three eval datasets, clause segmentation, verdicts, MCP server, Docker | Front-loaded data work in Week 1 that unblocks A, then the second surface and the second transport. |

**Track A is the bottleneck by design.** Weeks 1 and 2 of `docs/PLAN.md` are largely A work.
B and C are arranged so that neither ever waits on A, and so that both can converge onto A if it
slips. See [Slip protocol](#slip-protocol).

---

## Day 1: interface freeze (all three, together, before any feature work)

Three people building against unwritten interfaces produces three incompatible halves. Before
anyone starts, these types get written, agreed in one sitting, and merged to `main`. They are
already stubbed in the repo -- this is filling in the fields, not designing from scratch.

| Contract | File | Author | Consumers |
|---|---|---|---|
| `Identity` | `backend/app/auth.py` | M2 | A (every retrieval call), C (every MCP tool) |
| `RetrievedChunk`, `RetrievalResult` | `backend/app/retrieval/` | M1 | B (API responses), C (contract review) |
| `Answer`, `Citation` | `backend/app/generation/answer.py` | M1 | B (`AskResponse`, `types.ts`) |
| `Clause`, `Verdict`, `ClauseReview` | `backend/app/contracts/` | M3 | B (`ClauseVerdictOut`, verdict table) |
| Log function signatures | `backend/app/observability.py` | M2 | A calls all four from Week 1 |
| `Settings` fields | `backend/app/config.py` | shared | everyone |

Rules that come out of that session:

1. **`config.py` and `.env.example` are append-only.** Adding a field needs no discussion.
   Renaming or removing one gets announced before the PR, because it breaks the other two.
2. **A field in a frozen contract does not change silently.** If it must change, the owner says
   so in the group chat first, and the PR title starts with `contract:`.
3. **Nobody stubs around a missing interface.** If a type you need is not merged yet, that is a
   blocker to raise, not a local copy to make. Two copies of `Identity` is exactly how a
   permission check gets skipped on one path.

---

## File ownership map

One owner per file. If you need a change in someone else file, ask them or open a PR they review.
This is the merge-conflict prevention mechanism; treat it as binding.

| Path | Owner |
|---|---|
| `backend/app/ingestion/**` | M1 |
| `backend/app/retrieval/**` | M1 |
| `backend/app/generation/**` | M1 |
| `eval/metrics.py`, `eval/run_retrieval_eval.py` | M1 |
| `backend/tests/test_chunking.py`, `test_access_filter.py`, `test_adaptive_loop.py` | M1 |
| `backend/app/api/**` | M2 |
| `backend/app/auth.py`, `db.py`, `models.py`, `main.py`, `observability.py` | M2 |
| `frontend/**` | M2 |
| `backend/app/contracts/**` | M3 |
| `backend/app/mcp/**` | M3 |
| `backend/tests/test_clause_segmentation.py` | M3 |
| `eval/datasets/**`, `eval/run_contract_eval.py`, `eval/run_access_control_eval.py` | M3 |
| `data/**` (corpus, manifest, contracts) | M3 |
| `docker-compose.yml`, `backend/Dockerfile`, `frontend/Dockerfile` | M3 |
| `backend/app/config.py`, `.env.example` | shared, append-only |
| `docs/DECISIONS.md` | shared, append-only (one ADR per PR) |
| `docs/EVALUATION.md` | M1 writes retrieval tables, M3 writes contract + red-team tables |
| `docs/PLAN.md`, `docs/TEAM.md`, `README.md` | shared, changes announced |

---

## Track A — Retrieval Core & Evaluation (M1)

**You own the thing the project is graded on.** Non-negotiables 1, 3 and 4 in `CLAUDE.md` are
yours. If your track is late, the project has no result; if the UI is ugly, it has a result.

**Depends on:** the corpus and frozen Q&A set from M3 (Week 1), `Identity` and the log functions
from M2 (Day 1-3). Nothing else.

| Week | Tasks (PLAN.md refs) | Done when |
|---|---|---|
| 1 | Parsers + cleaning (1.4), chunking + its tests (1.5), embedder and Qdrant collections (1.6), corpus ingest (1.7), baseline fixed retrieval + cited generation (1.8), eval harness (1.9) | `precision@5`, `recall@5`, `MRR` for **Config A** recorded in `docs/EVALUATION.md` from a re-runnable script, with a full provenance block |
| 2 | Access filter + tests (2.2), engine wiring (2.3), evidence scoring (2.6), LangGraph loop (2.7), termination test (2.8), threshold calibration (2.9), A vs C run (2.10) | Sweep table published with the chosen threshold; A and C compared on the same frozen set in one table; the no-filter regression test is green |
| 3 | Expose the `policy_collection` retrieval path M3 needs (3.5 support); Config B **only if** Week 2 closed on time; blind-grade answer accuracy | M3 can call the engine for per-clause retrieval without touching Qdrant directly |
| 4 | Full comparative experiment (4.1), retrieval results write-up (4.6), report methods section | Every retrieval table in `docs/EVALUATION.md` has real numbers and provenance |

**Blocked on the corpus in Week 1?** Ask M3 for two sample documents on Day 1 and build parsing
and chunking against those. Do not author corpus documents yourself -- that is M3 scope and
duplicating it wastes a day.

**Hard rule for you specifically:** every PR that touches `access_filter.py` or `vector_store.py`
is reviewed by M2 or M3, never self-merged. You are too close to it to see a missing filter.

---

## Track B — Product Surface (M2)

**You own everything between the browser and the engine.** You are off the critical path on
purpose, which is what buys the team a real UI instead of a rushed one.

**Depends on:** M1 `RetrievalResult` / `Answer` for the `/ask` response shape (Day 1 freeze),
M3 contract types for the verdict table (Day 1 freeze). Not on their implementations -- build
against the frozen types with a fake, and swap the fake out when they land.

| Week | Tasks (PLAN.md refs) | Done when |
|---|---|---|
| 1 | `Identity` + demo users file + login (3.1, pulled forward), `create_app` + `/health`, PostgreSQL schema (3.10, pulled forward), **`observability.py` by Day 3** because M1 calls it from Week 1 | M1 can `from app.auth import Identity` and call all four log functions; `docker compose up` reaches a live `/health` |
| 2 | `/ask`, `/documents`, `/conversation/{id}` wired to M1 engine; conversation persistence; **start the Ask UI** | `/ask` returns a real cited answer end to end, and returns the insufficient-evidence answer as HTTP 200 with `sufficient=false` |
| 3 | Check UI + upload endpoint (3.3), documents view, citations, role badge, styling (3.2, 3.7) | Two demo users, same question, visibly different cited answers in the browser |
| 4 | Edge cases (4.4), demo rehearsal (4.7), report UI/architecture sections | Empty query, malformed upload, and no-match cases all handled without a stack trace |

**Deliberate deviation from `docs/PLAN.md`:** the plan puts all frontend work in Week 3, because
it assumes one person. You start the Ask UI in Week 2. The `CLAUDE.md` rule still stands for
everyone else -- **M1 and M3 do no UI work in Week 2**, no exceptions.

**Your one security duty:** the test that enumerates `app.routes` and fails if any route except
`/auth/login` and `/health` is missing `Depends(current_identity)`. Write it in Week 1, before
there are routes to forget about.

---

## Track C — Corpus, Contract Review, MCP & Infra (M3)

**Your Week 1 unblocks everyone.** Nothing in the project can be measured until the corpus and
the ground-truth set exist, so your first week is the most time-critical on the team even though
none of it is retrieval code.

**Depends on:** `Identity` from M2 (Day 1) for the MCP tools, M1 engine for per-clause retrieval
(Week 3). Your Week 1 depends on nobody.

| Week | Tasks (PLAN.md refs) | Done when |
|---|---|---|
| 1 | **Day 1: `docker compose up -d qdrant postgres ollama` working for all three of you.** Then the corpus (1.1): 10-15 documents across 3 departments with access tags, the manifest, one document only one demo user can see, one carrying the prompt-injection payload. Then the Q&A set (1.2) and the freeze (1.3) | Ground-truth set committed and its commit hash recorded in `docs/EVALUATION.md`; every document in the manifest has a department and an access level |
| 2 | Adversarial suite (2.4), minimal MCP server with `search_documents` only (2.5), run the red team through **both** transports with M1 | Per-item pass/fail recorded for HTTP and MCP in `docs/EVALUATION.md` section 5, judged on retrieved context and not on answer text |
| 3 | Clause segmentation + tests (3.4), per-clause retrieval via M1 engine (3.5), verdicts + disclaimer (3.6), remaining MCP tools (3.8), contract eval set + freeze (3.9) | An eval-set contract returns a verdict and a policy citation for every clause, with the disclaimer present in the API body **and** the MCP result |
| 4 | Contract evaluation run (4.2), red-team re-run on the shipped build (4.3), Docker build details + deploy (4.5), report contract section | Contract tables filled with a 4x4 confusion matrix; system answers from a browser pointed at the deployed instance |

**Do not write the corpus to fit the questions, or the questions to fit the corpus.** Write the
documents first as if a real company wrote them, then write questions against what is there.
M1 reviews your Q&A labels before the freeze -- a second pair of eyes on labels is cheap now and
expensive in Week 4 (see the label-correction procedure in `docs/EVALUATION.md`).

**Your one security duty:** MCP is a transport, not a trust boundary. Your tools take a token and
resolve it through `auth.verify_token`. If you ever find yourself accepting `department` or
`access_level` as a tool argument, stop -- that is client-supplied privilege escalation.

---

## Integration checkpoints

Five points where the three tracks must actually meet. Put them in the calendar now.

| # | When | Who | What must be true to pass |
|---|---|---|---|
| **CP0** | Day 1, together | all | Interface freeze merged; infra up on all three machines; `.env` filled and ADR-003 + ADR-005 decided and written down |
| **CP1** | End of Week 1 | M1 + M3 | Corpus ingested, Q&A set frozen, Config A numbers recorded |
| **CP2** | End of Week 2 | M1 + M3 | Red team green on both transports; threshold calibrated; A vs C table published. **This is the project result. Nothing else matters more.** |
| **CP3** | End of Week 3 | all | Ask and Check both demoable in the browser with live access control |
| **CP4** | Week 4 Day 2 | all | Every table in `docs/EVALUATION.md` filled with provenance |

CP2 is a joint working session, not a status update: M1 brings the filter and the loop, M3 brings
the adversarial suite and the MCP tool, and you run it together. A leak found by the person who
wrote the filter is rarer than a leak found by the person attacking it.

---

## Cross-track dependencies

| Blocked track | Waiting on | Needed by | If it is late |
|---|---|---|---|
| A (ingestion) | M3 corpus + manifest | W1 D3 | M3 hands over 2 sample documents on D1; A builds parsing/chunking against those |
| A (any retrieval) | M2 `Identity` | W1 D1 | Blocker. Escalate same day -- do not write a local `Identity` |
| A (logging) | M2 `observability.py` | W1 D3 | A calls the stubs; they raise until M2 fills them, which is visible and fine |
| B (`/ask`) | M1 engine | W2 D1 | B builds against the frozen `Answer` type with a hand-written fake result |
| B (verdict table) | M3 contract types | W3 D3 | Same: frozen types plus a fake |
| C (MCP tool) | A engine + M2 `verify_token` | W2 D3 | The tool is a thin wrapper; if the engine is a day late, wire the tool and test it against a fake |
| C (per-clause review) | A `policy_collection` path | W3 D3 | Blocker for verdicts. A prioritises this over Config B |
| all (results) | Frozen datasets | W1 end / W3 end | Never run a reported experiment against an unfrozen set |

---

## Git workflow

- One branch per track: `track/retrieval` (M1), `track/product` (M2), `track/contracts` (M3).
  Feature branches off your track branch, PRs into `main`.
- Nobody pushes to `main` directly, including for a one-line fix.
- Conventional-commit prefixes, per `CLAUDE.md`: `feat:`, `fix:`, `test:`, `docs:`, `chore:`.
  Add `contract:` for a change to a frozen interface.
- **Merge to `main` daily.** Three long-lived branches for a week is a fourth week of work you
  did not budget for.
- Review assignment: PRs are reviewed by whoever the change affects. The two mandatory ones are
  the access filter (reviewed by a non-M1) and the MCP tools (reviewed by M1, who owns the
  enforcement path the tools must not bypass).
- Never commit `.env`, `data/` contents, model weights, or `node_modules`.

## Slip protocol

Applies when a track misses a checkpoint. Decided now, so it is not negotiated under pressure.

1. **If A slips, everything else stops for A.** B pauses frontend work and pairs on the loop or
   the eval harness; C pauses MCP extras and takes over running sweeps and recording tables.
   Cut in the order given in `docs/PLAN.md`.
2. **If C Week 1 slips, the whole team writes corpus documents.** It is the one task that
   parallelises perfectly and the one nobody can start without.
3. **If B slips, ship the plain version.** A form and a JSON view demo the result just as well.
   The cut list in `docs/PLAN.md` is ordered; work down it, do not improvise.
4. **CP2 does not slip.** If Week 2 is at risk, cut Config B, cut the frontend, cut deployment --
   in that order -- before cutting anything in Sprint 2.

## Risks specific to a three-person split

| Risk | Likelihood | Mitigation | Fallback |
|---|---|---|---|
| Two people edit `config.py` and conflict every day | High | Append-only rule; add your fields early in Week 1 | Whoever conflicts rebases; never resolve by deleting the other field |
| A copy of `Identity` or the access check appears on a second path | Medium | Ownership map; cross-review on filter and MCP PRs; the no-filter regression test | Delete the copy, do not reconcile it |
| Track A becomes the single point of failure | High | B and C are scheduled to never wait on A; slip protocol converges the team onto A | Cut scope from B and C, never from A |
| Only one person understands the retrieval engine at demo time | Medium | M1 walks B and C through the loop at CP2, 30 minutes, before it is needed | Any of the three can run the eval harness by CP4 |
| Corpus author also writes the questions and grades the answers | High | M1 reviews labels before the freeze; shuffle configs before blind grading | State it as a limitation in the report, as `docs/EVALUATION.md` already does |
| Three machines, three sets of model tags and thresholds | Medium | `.env` values agreed at CP0; every result file records its own config | Discard results whose provenance does not match the agreed config |
| Merge-day integration surprise in Week 4 | Medium | Daily merges to `main`; CP1 to CP3 are integration checkpoints, not demos | Freeze features 48h before the deadline and integrate only |

## Report and demo split (Week 4)

| Section | Owner |
|---|---|
| Problem, architecture, related work | M2 |
| Ingestion, retrieval, adaptive loop, calibration method | M1 |
| Access control design + red-team results | M1 writes design, M3 writes results |
| Contract review design + results | M3 |
| Evaluation methodology + retrieval results | M1 |
| Limitations + future work | all, one paragraph each from your own track |
| Live demo driving | M2 (drives the UI), M1 narrates the loop, M3 narrates access control |
