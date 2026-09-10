/**
 * The signed-in user, department, and access level.
 *
 * Display only. It reflects the identity the backend already derived from the token; it never
 * influences what is retrieved. Prominent on purpose -- the live demo switches users, and the
 * audience has to see the switch.
 */

import { logoutAction } from "@/app/actions";
import type { Identity } from "@/lib/types";

export function RoleBadge({ identity }: { identity: Identity }) {
  return (
    <div className="role-badge">
      <span className="who">{identity.name}</span>
      <span className="tag tag-dept">{identity.department}</span>
      <span className="tag tag-level">{identity.accessLevel}</span>
      <form action={logoutAction}>
        <button className="secondary" type="submit" style={{ padding: "4px 10px" }}>
          Sign out
        </button>
      </form>
    </div>
  );
}
