/**
 * Root layout: shell, navigation between Ask / Check / Documents, and the role indicator.
 *
 * The department and role badge is part of the demo, not decoration: the access-control story is
 * shown by asking the same question as two different users and pointing at this badge.
 */

import type { Metadata } from "next";
import Link from "next/link";
import type { ReactNode } from "react";

import { RoleBadge } from "@/components/RoleBadge";
import { getSession } from "@/lib/session";

import "./globals.css";

export const metadata: Metadata = {
  title: process.env.NEXT_PUBLIC_APP_NAME ?? "Enterprise Knowledge Assistant",
  description: "Access-controlled document Q&A and contract compliance review.",
};

export default async function RootLayout({ children }: { children: ReactNode }) {
  const session = await getSession();

  return (
    <html lang="en">
      <body>
        <div className="shell">
          <header className="topbar">
            <span className="brand">
              {process.env.NEXT_PUBLIC_APP_NAME ?? "Enterprise Knowledge Assistant"}
            </span>
            {session ? (
              <>
                <nav className="nav">
                  <Link href="/ask">Ask</Link>
                  <Link href="/check">Check</Link>
                  <Link href="/documents">Documents</Link>
                </nav>
                <div className="spacer" />
                <RoleBadge identity={session.identity} />
              </>
            ) : null}
          </header>
          <main>{children}</main>
        </div>
      </body>
    </html>
  );
}
