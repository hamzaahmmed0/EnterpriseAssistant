/**
 * Documents: what the signed-in user is authorized to see, with access tags shown.
 */

export default function DocumentsPage() {
  throw new Error("Not implemented");
}

// TODO:
//  1. Server-side: read the session, call lib/api.listDocuments, render the table.
//  2. Show department and access level per document -- this list is the visible proof that two
//     users see different corpora.
//  3. Render an empty state rather than an error when the caller can see nothing.
