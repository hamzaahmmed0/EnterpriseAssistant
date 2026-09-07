/**
 * Check: upload a contract and read the clause-by-clause compliance report.
 */

export default function CheckPage() {
  throw new Error("Not implemented");
}

// TODO:
//  1. Server-side: read the session, redirect if absent.
//  2. Render ContractUpload, then ClauseVerdictTable once the review returns.
//  3. Render the disclaimer from the API response verbatim, above the results, always.
//  4. Show processing status; review is slow with a local model, so a silent wait reads as a hang.
//  5. Handle the rejection paths (wrong type, too large) with a clear message.
