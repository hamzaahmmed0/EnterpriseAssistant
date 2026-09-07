"""Prompt templates.

Prompts are part of the experimental configuration: changing one invalidates comparisons across
configs, so every template is versioned and the version goes in the eval provenance block.
"""

ANSWER_SYSTEM_PROMPT_VERSION = "v0"
CLAUSE_VERDICT_PROMPT_VERSION = "v0"


def answer_system_prompt() -> str:
    """System prompt enforcing context-only answering with required citations."""
    raise NotImplementedError


def answer_user_prompt(question: str, context_blocks: list[str]) -> str:
    """Render the question and numbered context blocks into the user prompt."""
    raise NotImplementedError


def clause_verdict_prompt(clause_text: str, policy_blocks: list[str]) -> str:
    """Render the clause-versus-policy comparison prompt returning a structured verdict."""
    raise NotImplementedError


def reformulation_prompt(original_query: str, previous_query: str) -> str:
    """Render the prompt that rewrites a query after an insufficient-evidence attempt."""
    raise NotImplementedError


# TODO:
#  1. Write answer_system_prompt(): answer only from the supplied context, cite the block ids
#     used, and say "insufficient evidence" rather than guessing. Never instruct the model to be
#     helpful at the cost of grounding.
#  2. Number context blocks so a citation maps back to a (document_id, page) deterministically.
#  3. Write clause_verdict_prompt() constraining output to the four verdict labels plus a cited
#     policy section and a short explanation, as strict JSON.
#  4. Write reformulation_prompt() (blocked on ADR-004 open question 4).
#  5. Bump the version constants on any prompt edit, and re-run affected configurations.
#  6. Add a note in the contract prompt that its output is decision support, not legal advice --
#     the label is enforced in code (ADR-010), not left to the model.
