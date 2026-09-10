import "server-only";

/**
 * Demo session handling: storing the token issued by /auth/login and reading it back server-side.
 *
 * The identity stored alongside the token is display data only. The backend re-derives
 * authorization from the token signature on every request and is the only place that decides
 * access -- nothing here can widen what a user can see.
 */

import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import type { Identity } from "./types";

const TOKEN_COOKIE = "eka_token";
const IDENTITY_COOKIE = "eka_identity";

/** Cookie lifetime in seconds. Mirrors AUTH_TOKEN_TTL_MINUTES so the UI and token expire together. */
const MAX_AGE_SECONDS = Number(process.env.AUTH_TOKEN_TTL_MINUTES ?? 480) * 60;

export interface Session {
  token: string;
  identity: Identity;
}

export async function setSession(token: string, identity: Identity): Promise<void> {
  const store = await cookies();
  const options = {
    httpOnly: true,
    sameSite: "lax" as const,
    secure: process.env.NODE_ENV === "production",
    path: "/",
    maxAge: MAX_AGE_SECONDS,
  };

  // httpOnly on both: the token must never be readable from client JS, and the identity is only
  // ever rendered server-side, so there is no reason to expose it either.
  store.set(TOKEN_COOKIE, token, options);
  store.set(IDENTITY_COOKIE, JSON.stringify(identity), options);
}

export async function getSession(): Promise<Session | null> {
  const store = await cookies();
  const token = store.get(TOKEN_COOKIE)?.value;
  const rawIdentity = store.get(IDENTITY_COOKIE)?.value;

  if (!token || !rawIdentity) return null;

  try {
    return { token, identity: JSON.parse(rawIdentity) as Identity };
  } catch {
    return null;
  }
}

/** Get the session or send the visitor to the login page. Used by every authenticated page. */
export async function requireSession(): Promise<Session> {
  const session = await getSession();
  if (!session) redirect("/");
  return session;
}

export async function clearSession(): Promise<void> {
  const store = await cookies();
  store.delete(TOKEN_COOKIE);
  store.delete(IDENTITY_COOKIE);
}
