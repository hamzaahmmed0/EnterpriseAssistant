/**
 * Root layout: shell, navigation between Ask / Check / Documents, and the role indicator.
 *
 * The department and role badge is part of the demo, not decoration: the access-control story is
 * shown by asking the same question as two different users.
 */

import type { ReactNode } from "react";

export default function RootLayout({ children }: { children: ReactNode }) {
  throw new Error("Not implemented");
}

// TODO:
//  1. Render html/body, global styles, and the nav shell.
//  2. Read the session server-side and render RoleBadge; redirect to / when there is no session.
//  3. Add the metadata export (title from NEXT_PUBLIC_APP_NAME).
