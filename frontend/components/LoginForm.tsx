"use client";

/**
 * Demo login form. Submits through a server action so no token ever reaches client JS.
 */

import { useActionState } from "react";

import { loginAction, type LoginState } from "@/app/actions";

interface DemoUser {
  id: string;
  name: string;
  department: string;
  level: string;
}

export function LoginForm({ users }: { users: DemoUser[] }) {
  const [state, formAction, pending] = useActionState<LoginState, FormData>(loginAction, {});

  return (
    <form action={formAction}>
      {state.error ? <p className="error">{state.error}</p> : null}

      <div className="field">
        <label htmlFor="user_id">Demo user</label>
        <select id="user_id" name="user_id" defaultValue={users[0]?.id}>
          {users.map((user) => (
            <option key={user.id} value={user.id}>
              {user.name} — {user.department} / {user.level}
            </option>
          ))}
        </select>
      </div>

      <div className="field">
        <label htmlFor="password">Password</label>
        <input id="password" name="password" type="password" autoComplete="current-password" />
      </div>

      <button type="submit" disabled={pending}>
        {pending ? "Signing in…" : "Sign in"}
      </button>
    </form>
  );
}
