/**
 * Source citations under an answer.
 *
 * Citation is required, not decorative: an answer that claims to be grounded but cites nothing is
 * a failure state and is rendered as one rather than as an empty space.
 */

import type { Citation } from "@/lib/types";

interface CitationListProps {
  citations: Citation[];
  /** Whether the answer claimed to be grounded. An uncited grounded answer is a defect. */
  sufficient: boolean;
}

export function CitationList({ citations, sufficient }: CitationListProps) {
  if (citations.length === 0) {
    if (!sufficient) return null; // the fallback has nothing to cite, correctly
    return (
      <p className="citations none">
        This answer carries no citations, which should not happen. Treat it as unverified.
      </p>
    );
  }

  return (
    <div className="citations">
      <strong>Sources</strong>
      <ol>
        {citations.map((citation) => (
          <li key={citation.chunkId}>
            {citation.documentTitle} — page {citation.page}
          </li>
        ))}
      </ol>
    </div>
  );
}
