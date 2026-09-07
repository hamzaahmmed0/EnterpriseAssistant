"""REST endpoints: /auth/login, /documents, /ask, /check-contract, /conversation/{id}.

Routes stay thin. They resolve an Identity, hand it to the engine or the reviewer, and shape the
reply. No retrieval logic, no filtering, no access decisions taken here -- those belong to
retrieval.access_filter, and duplicating them here would create a second place to get it wrong.
"""

from fastapi import APIRouter, UploadFile

from app.api.schemas import (
    AskRequest,
    AskResponse,
    CheckContractResponse,
    ConversationResponse,
    DocumentOut,
    LoginRequest,
    LoginResponse,
)
from app.auth import Identity

router = APIRouter()


async def login(payload: LoginRequest) -> LoginResponse:
    """Authenticate a demo user and return a session token."""
    raise NotImplementedError


async def list_documents(identity: Identity) -> list[DocumentOut]:
    """List documents the caller is authorized to see."""
    raise NotImplementedError


async def ask(payload: AskRequest, identity: Identity) -> AskResponse:
    """Answer a question from permission-filtered context, with citations."""
    raise NotImplementedError


async def check_contract(file: UploadFile, identity: Identity) -> CheckContractResponse:
    """Review an uploaded contract clause by clause against policy."""
    raise NotImplementedError


async def get_conversation(conversation_id: str, identity: Identity) -> ConversationResponse:
    """Return a conversation transcript, if it belongs to the caller."""
    raise NotImplementedError


# TODO:
#  1. Register each function on `router` with its decorator, path, and response_model.
#  2. Add Depends(current_identity) to every route except login.
#  3. Implement list_documents() by querying PostgreSQL with the same visibility rule the vector
#     filter uses -- derive both from access_filter.visible_access_levels so they cannot diverge.
#  4. Implement ask(): engine.retrieve -> generate_answer -> persist message -> respond. Return
#     the insufficient-evidence answer with HTTP 200; it is an answer, not an error.
#  5. Implement check_contract(): validate_upload -> save to data/contracts -> review_contract,
#     and always populate the disclaimer field.
#  6. Implement get_conversation() with an ownership check that 404s rather than 403s.
#  7. Decide whether /ask streams (proposal section 12) -- streaming is on the cut list in
#     docs/PLAN.md, so build the non-streaming path first.
#  8. API tests for /ask, /documents, /check-contract, including the unauthorized-caller case for
#     each.
