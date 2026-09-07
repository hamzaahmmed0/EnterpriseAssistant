/**
 * Clause-by-clause compliance report.
 */

import type { ClauseVerdict } from "@/lib/types";

export interface ClauseVerdictTableProps {
  clauses: ClauseVerdict[];
  disclaimer: string;
}

export function ClauseVerdictTable({ clauses, disclaimer }: ClauseVerdictTableProps) {
  throw new Error("Not implemented");
}

// TODO:
//  1. Colour-code the four verdicts, and pair colour with a text label so the status does not
//     depend on colour alone.
//  2. Render the cited policy document and section per clause; a verdict without a citation is
//     displayed as such rather than left blank.
//  3. Render the disclaimer prominently and unconditionally (ADR-010).
//  4. Keep long clause text collapsible so the table stays readable.
