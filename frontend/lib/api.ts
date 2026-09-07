/**
 * Server-side client for the backend API.
 *
 * Every function here runs on the Next.js server, never in the browser: the backend URL and the
 * session token must not reach client bundles, and the browser must never call Qdrant or the LLM.
 */

import type {
  AskResponse,
  ContractReviewResponse,
  DocumentSummary,
  Identity,
} from "./types";

export async function login(userId: string, password: string): Promise<{ token: string; identity: Identity }> {
  throw new Error("Not implemented");
}

export async function ask(token: string, question: string, conversationId?: string): Promise<AskResponse> {
  throw new Error("Not implemented");
}

export async function listDocuments(token: string): Promise<DocumentSummary[]> {
  throw new Error("Not implemented");
}

export async function checkContract(token: string, file: File): Promise<ContractReviewResponse> {
  throw new Error("Not implemented");
}

// TODO:
//  1. Read BACKEND_INTERNAL_URL from server env only; throw at module load if it is missing.
//  2. Add a shared request helper handling the Authorization header, timeouts, and error mapping.
//  3. Surface an insufficient-evidence answer as a normal result, not an error -- it arrives as
//     HTTP 200 with sufficient=false.
//  4. Mark this module server-only so an accidental client import fails the build rather than
//     leaking the backend URL.
//  5. Stream /ask only if streaming survives the cut list in docs/PLAN.md.
