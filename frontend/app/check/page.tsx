/**
 * Check: upload a contract and read the clause-by-clause compliance report.
 */

import { ContractCheck } from "@/components/ContractCheck";
import { requireSession } from "@/lib/session";

export default async function CheckPage() {
  await requireSession();

  return (
    <>
      <h1>Check a contract</h1>
      <p className="lede">
        Each clause is compared against the internal policy you are authorised to read. Clauses
        with no applicable policy are returned as Needs Legal Review rather than assumed
        compliant.
      </p>
      <ContractCheck />
    </>
  );
}
