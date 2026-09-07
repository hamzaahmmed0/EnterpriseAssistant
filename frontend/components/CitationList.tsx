/**
 * Source citations under an answer.
 *
 * Citation is required, not decorative: an answer with no citations is a failure state and must
 * be rendered as one rather than silently showing nothing.
 */

import type { Citation } from "@/lib/types";

export interface CitationListProps {
  citations: Citation[];
}

export function CitationList({ citations }: CitationListProps) {
  throw new Error("Not implemented");
}

// TODO:
//  1. Render document title and page per citation.
//  2. Render an explicit "no sources" state when the list is empty on a sufficient answer.
//  3. Decide whether a citation links to the source document, and whether that link is itself
//     access-checked -- if it is not, it is a second retrieval path without a filter.
