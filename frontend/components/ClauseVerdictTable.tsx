/**
 * Clause-by-clause compliance report.
 *
 * The disclaimer renders unconditionally and above the results (ADR-010). Verdicts pair colour
 * with a text label, so the status never depends on colour alone.
 */

import { VERDICT_STYLES, type ClauseVerdict } from "@/lib/types";

interface ClauseVerdictTableProps {
  clauses: ClauseVerdict[];
  disclaimer: string;
  contractName: string;
  segmentationPath: string;
}

export function ClauseVerdictTable({
  clauses,
  disclaimer,
  contractName,
  segmentationPath,
}: ClauseVerdictTableProps) {
  return (
    <>
      <p className="disclaimer">{disclaimer}</p>

      <div className="card">
        <h2 style={{ fontSize: 15, margin: "0 0 4px" }}>{contractName}</h2>
        <p className="lede" style={{ margin: "0 0 16px", fontSize: 13 }}>
          {clauses.length} clause{clauses.length === 1 ? "" : "s"}, segmented via{" "}
          {segmentationPath}.
        </p>

        {clauses.length === 0 ? (
          <p className="empty">
            No clauses could be segmented from this document. Check that it is a text-based PDF or
            DOCX rather than a scan.
          </p>
        ) : (
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Clause</th>
                  <th>Verdict</th>
                  <th>Policy cited</th>
                  <th>Why</th>
                </tr>
              </thead>
              <tbody>
                {clauses.map((clause) => {
                  const style = VERDICT_STYLES[clause.verdict];
                  return (
                    <tr key={clause.clauseIndex}>
                      <td style={{ minWidth: 180 }}>
                        <strong>{clause.heading || `Clause ${clause.clauseIndex + 1}`}</strong>
                        <details>
                          <summary>Show text</summary>
                          <p className="clause-text">{clause.clauseText}</p>
                        </details>
                      </td>
                      <td>
                        <span className={`verdict ${style.className}`}>{style.label}</span>
                      </td>
                      <td>
                        {clause.citedPolicyDoc ? (
                          <>
                            {clause.citedPolicyDoc}
                            {clause.citedPolicySection ? ` (${clause.citedPolicySection})` : ""}
                          </>
                        ) : (
                          <span style={{ color: "var(--muted)" }}>none cited</span>
                        )}
                      </td>
                      <td>{clause.explanation}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </>
  );
}
