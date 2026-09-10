"use client";

/**
 * Upload flow plus the clause-by-clause report for the Check surface.
 */

import { useActionState } from "react";

import { checkContractAction, type CheckState } from "@/app/actions";
import { ClauseVerdictTable } from "@/components/ClauseVerdictTable";

const EMPTY: CheckState = {};

export function ContractCheck() {
  const [state, formAction, pending] = useActionState<CheckState, FormData>(
    checkContractAction,
    EMPTY,
  );

  return (
    <>
      <form action={formAction} className="card">
        <div className="field">
          <label htmlFor="file">Contract (PDF or DOCX, max 10 MB)</label>
          <input
            id="file"
            name="file"
            type="file"
            accept=".pdf,.docx"
            required
            disabled={pending}
          />
        </div>
        <button type="submit" disabled={pending}>
          {pending ? "Reviewing…" : "Review contract"}
        </button>
        {pending ? (
          <p className="pending" style={{ marginBottom: 0 }}>
            Every clause is retrieved and compared separately, so this takes a while on a local
            model.
          </p>
        ) : null}
      </form>

      {state.error ? <p className="error">{state.error}</p> : null}

      {state.result ? (
        <ClauseVerdictTable
          clauses={state.result.clauses}
          disclaimer={state.result.disclaimer}
          contractName={state.result.contractName}
          segmentationPath={state.result.segmentationPath}
        />
      ) : null}
    </>
  );
}
