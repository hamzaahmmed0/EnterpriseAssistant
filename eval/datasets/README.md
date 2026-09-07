# Eval datasets

Schemas are specified in `docs/EVALUATION.md` section 1 and are authoritative. The `*.example.json`
files here are **shape references with placeholder content**, not data. They exist so the harness
can be written against a concrete schema before the real sets are authored.

| File | Authored in | Frozen at |
|---|---|---|
| `qa_ground_truth.json` | Sprint 1, tasks 1.2 | end of Sprint 1 (task 1.3) |
| `adversarial_queries.json` | Sprint 2, task 2.4 | when first run (task 2.5) |
| `contracts_labeled.json` | Sprint 3, task 3.9 | end of Sprint 3 |

Once frozen, record the commit hash in `docs/EVALUATION.md`. Corrections follow the procedure
there: fix, log, re-run every configuration.

TODO: delete the `.example.json` files once the real sets exist, so there is no ambiguity about
which file the harness reads.
