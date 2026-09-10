/**
 * Shared TypeScript types mirroring the backend API schemas.
 *
 * Decision (the open question in the original stub): the API speaks snake_case, and mapping to
 * camelCase happens in exactly one place -- `lib/api.ts`. Components never see wire shapes, and
 * there is one file to fix when a field is renamed. A per-endpoint mix is how a required field
 * like the legal disclaimer goes missing on one screen and not another.
 *
 * These must stay in lockstep with backend/app/api/schemas.py.
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

export interface AskResult {
  answer: string;
  citations: Citation[];
  /** False means the honest fallback was returned. It is a normal result, not an error. */
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

export interface ContractReviewResult {
  contractReviewId: string;
  contractName: string;
  clauses: ClauseVerdict[];
  segmentationPath: string;
  /** Decision-support disclaimer. Required by ADR-010; never optional, never rendered away. */
  disclaimer: string;
  latencySeconds: number;
}

export interface ChatTurn {
  role: "user" | "assistant";
  content: string;
  result?: AskResult;
}

/** Verdict presentation. Colour is paired with a label so status never depends on colour alone. */
export const VERDICT_STYLES: Record<Verdict, { label: string; className: string }> = {
  Compliant: { label: "Compliant", className: "verdict-compliant" },
  Deviates: { label: "Deviates", className: "verdict-deviates" },
  Missing: { label: "Missing", className: "verdict-missing" },
  "Needs Legal Review": { label: "Needs Legal Review", className: "verdict-review" },
};
