/**
 * The signed-in user, department, and access level.
 *
 * Display only. It reflects the identity the backend already derived from the token; it never
 * influences what is retrieved.
 */

import type { Identity } from "@/lib/types";

export interface RoleBadgeProps {
  identity: Identity;
}

export function RoleBadge({ identity }: RoleBadgeProps) {
  throw new Error("Not implemented");
}

// TODO:
//  1. Render name, department, and access level, plus a sign-out action.
//  2. Make it prominent -- the live demo switches users, and the audience has to see the switch.
