/**
 * Demo session handling: storing the token issued by /auth/login and reading it back server-side.
 */

import type { Identity } from "./types";

export async function setSession(token: string, identity: Identity): Promise<void> {
  throw new Error("Not implemented");
}

export async function getSession(): Promise<{ token: string; identity: Identity } | null> {
  throw new Error("Not implemented");
}

export async function clearSession(): Promise<void> {
  throw new Error("Not implemented");
}

// TODO:
//  1. Store the token in an httpOnly, sameSite cookie -- never localStorage.
//  2. Treat the identity in the cookie as display data only; the backend re-derives authorization
//     from the token on every request and is the only place that decides access.
//  3. Redirect to the login page when getSession() returns null.
//  4. Honour AUTH_TOKEN_TTL_MINUTES on the cookie so the UI and the token expire together.
