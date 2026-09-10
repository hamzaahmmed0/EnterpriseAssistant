"use server";

/**
 * Server actions. Every one of these runs on the server with the session cookie, so the browser
 * never holds a token and never speaks to the backend directly.
 */

import { redirect } from "next/navigation";

import { ApiError, ask as askApi, checkContract, login } from "@/lib/api";
import { clearSession, requireSession, setSession } from "@/lib/session";
import type { AskResult, ContractReviewResult } from "@/lib/types";

export interface LoginState {
  error?: string;
}

export async function loginAction(
  _previous: LoginState,
  formData: FormData,
): Promise<LoginState> {
  const userId = String(formData.get("user_id") ?? "").trim();
  const password = String(formData.get("password") ?? "");

  if (!userId || !password) {
    return { error: "Enter a user and a password." };
  }

  try {
    const { token, identity } = await login(userId, password);
    await setSession(token, identity);
  } catch (error) {
    // Deliberately generic: the message must not reveal whether the user id exists.
    if (error instanceof ApiError && error.status >= 500) {
      return { error: "The backend is unavailable. Is it running?" };
    }
    return { error: "Invalid credentials." };
  }

  redirect("/ask");
}

export async function logoutAction(): Promise<void> {
  await clearSession();
  redirect("/");
}

export interface AskState {
  turns: { role: "user" | "assistant"; content: string; result?: AskResult }[];
  conversationId?: string;
  error?: string;
}

export async function askAction(previous: AskState, formData: FormData): Promise<AskState> {
  const question = String(formData.get("question") ?? "").trim();
  if (!question) {
    return { ...previous, error: "Type a question first." };
  }

  const { token } = await requireSession();
  const turns = [...previous.turns, { role: "user" as const, content: question }];

  try {
    const result = await askApi(token, question, previous.conversationId);
    return {
      turns: [...turns, { role: "assistant" as const, content: result.answer, result }],
      conversationId: result.conversationId,
    };
  } catch (error) {
    const message =
      error instanceof ApiError ? error.message : "Something went wrong asking that question.";
    return { turns, conversationId: previous.conversationId, error: message };
  }
}

export interface CheckState {
  result?: ContractReviewResult;
  error?: string;
}

export async function checkContractAction(
  _previous: CheckState,
  formData: FormData,
): Promise<CheckState> {
  const file = formData.get("file");
  if (!(file instanceof File) || file.size === 0) {
    return { error: "Choose a PDF or DOCX contract to review." };
  }

  const { token } = await requireSession();
  try {
    return { result: await checkContract(token, file) };
  } catch (error) {
    const message =
      error instanceof ApiError ? error.message : "The contract could not be reviewed.";
    return { error: message };
  }
}
