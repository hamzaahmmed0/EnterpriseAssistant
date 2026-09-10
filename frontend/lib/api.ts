import "server-only";

/**
 * Server-side client for the backend API.
 *
 * Every function here runs on the Next.js server, never in the browser: the backend URL and the
 * session token must not reach client bundles, and the browser must never call Qdrant or the LLM.
 * The `server-only` import above turns an accidental client import into a build error rather than
 * a silent leak.
 *
 * This is also the single snake_case -> camelCase boundary (see lib/types.ts).
 */

import type {
  AskResult,
  Citation,
  ClauseVerdict,
  ContractReviewResult,
  DocumentSummary,
  Identity,
  Verdict,
} from "./types";

const DEFAULT_TIMEOUT_MS = 240_000; // local generation is slow; see docs/EVALUATION.md on latency

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

function backendUrl(): string {
  const url = process.env.BACKEND_INTERNAL_URL;
  if (!url) {
    throw new Error(
      "BACKEND_INTERNAL_URL is not set. It is server-side only and must never be NEXT_PUBLIC_.",
    );
  }
  return url.replace(/\/$/, "");
}

async function request<T>(
  path: string,
  init: RequestInit & { token?: string } = {},
): Promise<T> {
  const { token, headers, ...rest } = init;
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), DEFAULT_TIMEOUT_MS);

  try {
    const response = await fetch(`${backendUrl()}${path}`, {
      ...rest,
      headers: {
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
        ...headers,
      },
      cache: "no-store",
      signal: controller.signal,
    });

    if (!response.ok) {
      let detail = response.statusText;
      try {
        const body = (await response.json()) as { detail?: string };
        detail = body.detail ?? detail;
      } catch {
        // Non-JSON error body; the status text is all we have.
      }
      throw new ApiError(detail, response.status);
    }

    return (await response.json()) as T;
  } catch (error) {
    if (error instanceof ApiError) throw error;
    if (error instanceof Error && error.name === "AbortError") {
      throw new ApiError("The backend did not respond in time.", 504);
    }
    throw new ApiError("Could not reach the backend.", 503);
  } finally {
    clearTimeout(timeout);
  }
}

// --------------------------------------------------------------------------- mapping

interface WireCitation {
  document_id: string;
  document_title: string;
  page: number;
  chunk_id: string;
}

function toCitation(wire: WireCitation): Citation {
  return {
    documentId: wire.document_id,
    documentTitle: wire.document_title,
    page: wire.page,
    chunkId: wire.chunk_id,
  };
}

// --------------------------------------------------------------------------- endpoints

export async function login(
  userId: string,
  password: string,
): Promise<{ token: string; identity: Identity }> {
  const wire = await request<{
    token: string;
    user_id: string;
    name: string;
    department: string;
    role: string;
    access_level: string;
  }>("/auth/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ user_id: userId, password }),
  });

  return {
    token: wire.token,
    identity: {
      userId: wire.user_id,
      name: wire.name,
      department: wire.department,
      role: wire.role,
      accessLevel: wire.access_level,
    },
  };
}

export async function ask(
  token: string,
  question: string,
  conversationId?: string,
): Promise<AskResult> {
  const wire = await request<{
    answer: string;
    citations: WireCitation[];
    sufficient: boolean;
    evidence_score: number;
    attempts: number;
    conversation_id: string;
    latency_seconds: number;
  }>("/ask", {
    token,
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question, conversation_id: conversationId ?? null }),
  });

  return {
    answer: wire.answer,
    citations: wire.citations.map(toCitation),
    sufficient: wire.sufficient,
    evidenceScore: wire.evidence_score,
    attempts: wire.attempts,
    conversationId: wire.conversation_id,
    latencySeconds: wire.latency_seconds,
  };
}

export async function listDocuments(token: string): Promise<DocumentSummary[]> {
  const wire = await request<
    {
      document_id: string;
      title: string;
      department: string;
      access_level: string;
      page_count: number;
    }[]
  >("/documents", { token });

  return wire.map((row) => ({
    documentId: row.document_id,
    title: row.title,
    department: row.department,
    accessLevel: row.access_level,
    pageCount: row.page_count,
  }));
}

export async function checkContract(
  token: string,
  file: File,
): Promise<ContractReviewResult> {
  const form = new FormData();
  form.append("file", file, file.name);

  const wire = await request<{
    contract_review_id: string;
    contract_name: string;
    clauses: {
      clause_index: number;
      heading: string;
      clause_text: string;
      verdict: Verdict;
      cited_policy_doc: string | null;
      cited_policy_section: string | null;
      explanation: string;
    }[];
    segmentation_path: string;
    disclaimer: string;
    latency_seconds: number;
  }>("/check-contract", { token, method: "POST", body: form });

  const clauses: ClauseVerdict[] = wire.clauses.map((clause) => ({
    clauseIndex: clause.clause_index,
    heading: clause.heading,
    clauseText: clause.clause_text,
    verdict: clause.verdict,
    citedPolicyDoc: clause.cited_policy_doc,
    citedPolicySection: clause.cited_policy_section,
    explanation: clause.explanation,
  }));

  if (!wire.disclaimer) {
    // ADR-010: the disclaimer is required at every exit point. If the backend ever stops sending
    // it, fail loudly here rather than rendering a compliance report that reads as legal advice.
    throw new ApiError("Contract review response is missing its legal disclaimer.", 500);
  }

  return {
    contractReviewId: wire.contract_review_id,
    contractName: wire.contract_name,
    clauses,
    segmentationPath: wire.segmentation_path,
    disclaimer: wire.disclaimer,
    latencySeconds: wire.latency_seconds,
  };
}
