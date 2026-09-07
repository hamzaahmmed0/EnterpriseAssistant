/**
 * Shared TypeScript types mirroring the backend API schemas.
 *
 * These must stay in lockstep with backend/app/api/schemas.py. If they drift, the UI will
 * silently render stale fields -- including the legal disclaimer, which is not optional.
 */

export interface Identity {
  userId: string;
  name: string;
  department: string;
  role: string;
  accessLevel: string;
}

export interface Citation {
  documentId: string;
  documentTitle: string;
  page: number;
  chunkId: string;
}

export interface AskResponse {
  answer: string;
  citations: Citation[];
  sufficient: boolean;
  evidenceScore: number;
  attempts: number;
  conversationId: string;
  latencySeconds: number;
}

export interface DocumentSummary {
  documentId: string;
  title: string;
  department: string;
  accessLevel: string;
  pageCount: number;
}

export type Verdict = "Compliant" | "Deviates" | "Missing" | "Needs Legal Review";

export interface ClauseVerdict {
  clauseIndex: number;
  heading: string;
  clauseText: string;
  verdict: Verdict;
  citedPolicyDoc: string | null;
  citedPolicySection: string | null;
  explanation: string;
}

export interface ContractReviewResponse {
  contractReviewId: string;
  contractName: string;
  clauses: ClauseVerdict[];
  /** Decision-support disclaimer. Required by ADR-010; never optional, never rendered away. */
  disclaimer: string;
  latencySeconds: number;
}

// TODO:
//  1. Decide whether the API emits snake_case and the client maps it, or the API emits camelCase.
//     Pick one and apply it everywhere; a per-endpoint mix is how the disclaimer goes missing.
//  2. Generate these from the backend OpenAPI schema once the routes are implemented, rather than
//     maintaining two hand-written copies.
