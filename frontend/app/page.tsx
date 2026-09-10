/**
 * Login page: pick one of the demo users and sign in.
 *
 * The user list shows each demo user's department and access level, so a viewer can see which
 * boundary they sit on before switching -- that comparison is the access-control demo.
 */

import { redirect } from "next/navigation";

import { LoginForm } from "@/components/LoginForm";
import { getSession } from "@/lib/session";

const DEMO_USERS = [
  { id: "hr_generalist", name: "Ayesha Khan", department: "hr", level: "internal" },
  { id: "hr_director", name: "Marta Silva", department: "hr", level: "confidential" },
  { id: "eng_ic", name: "Daniel Osei", department: "engineering", level: "internal" },
  { id: "fin_controller", name: "Priya Raman", department: "finance", level: "confidential" },
];

export default async function LoginPage() {
  if (await getSession()) redirect("/ask");

  return (
    <>
      <h1>Sign in</h1>
      <p className="lede">
        Demo accounts only. Access control is enforced in the retrieval layer, so what each user
        can retrieve differs by department and access level.
      </p>

      <div className="card">
        <LoginForm users={DEMO_USERS} />
      </div>

      <div className="card">
        <h2 style={{ fontSize: 15, margin: "0 0 10px" }}>Who sees what</h2>
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th>User</th>
                <th>Department</th>
                <th>Access level</th>
              </tr>
            </thead>
            <tbody>
              {DEMO_USERS.map((user) => (
                <tr key={user.id}>
                  <td>
                    {user.name} <span style={{ color: "var(--muted)" }}>({user.id})</span>
                  </td>
                  <td>
                    <span className="tag tag-dept">{user.department}</span>
                  </td>
                  <td>
                    <span className="tag tag-level">{user.level}</span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="lede" style={{ margin: "12px 0 0", fontSize: 13 }}>
          The two HR accounts differ only by access level; the Engineering account sits on the
          other side of the department partition. Ask all three the same question to see it.
        </p>
      </div>
    </>
  );
}
