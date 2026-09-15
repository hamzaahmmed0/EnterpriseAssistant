"""Smoke-test the access-control demo against a running API.

Logs in as two HR users at different access levels and asks the SAME question about the
HR-confidential compensation bands. The director (confidential) should get a cited answer;
the generalist (internal) should get the insufficient-evidence fallback, because the
restricted chunks are filtered out *before* the search runs, not after.

Run (API must be up on 127.0.0.1:8000):  python eval/smoke_access_demo.py
"""

from __future__ import annotations

import json
import sys
import urllib.request

API = "http://127.0.0.1:8000"
DEMO_PASSWORD = "demo1234"  # documented in README.md; synthetic demo credential


def _post(path: str, payload: dict, token: str | None = None) -> dict:
    data = json.dumps(payload).encode()
    req = urllib.request.Request(f"{API}{path}", data=data, method="POST")
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(req, timeout=120) as resp:
        return json.loads(resp.read())


def login(user_id: str) -> str:
    return _post("/auth/login", {"user_id": user_id, "password": DEMO_PASSWORD})["token"]


def ask(token: str, question: str) -> dict:
    return _post("/ask", {"question": question}, token=token)


def show(user_id: str, result: dict) -> None:
    print(f"\n{'=' * 70}\nUSER: {user_id}")
    print(f"{'=' * 70}")
    answer = result.get("answer", "")
    citations = result.get("citations", [])
    print(f"answer      : {answer[:600]}")
    print(f"sufficient  : {result.get('sufficient')}")
    print(f"evidence    : {result.get('evidence_score')}")
    print(f"attempts    : {result.get('attempts')}")
    print(f"citations   : {[c.get('document_id') for c in citations]}")


def main() -> int:
    question = "What is our compensation and pay review policy?"
    print(f"QUESTION (asked by both users): {question!r}")

    for user_id in ("people_director", "people_member"):
        token = login(user_id)
        show(user_id, ask(token, question))

    print(f"\n{'=' * 70}")
    print("EXPECTED: people_director gets an answer cited to a People/confidential compensation doc;")
    print("          people_member gets 'insufficient evidence' with no confidential citation.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
