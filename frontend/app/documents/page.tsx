/**
 * Documents: what the signed-in user is authorised to see, with access tags shown.
 *
 * This list is the visible proof that two users see different corpora -- it is derived from the
 * same visibility rule as the vector pre-filter, not a separate one.
 */

import { ApiError, listDocuments } from "@/lib/api";
import { requireSession } from "@/lib/session";

export default async function DocumentsPage() {
  const { token, identity } = await requireSession();

  let documents;
  try {
    documents = await listDocuments(token);
  } catch (error) {
    const message = error instanceof ApiError ? error.message : "Could not load documents.";
    return (
      <>
        <h1>Documents</h1>
        <p className="error">{message}</p>
      </>
    );
  }

  return (
    <>
      <h1>Documents</h1>
      <p className="lede">
        {documents.length} document{documents.length === 1 ? "" : "s"} visible to {identity.name}{" "}
        ({identity.department} / {identity.accessLevel}).
      </p>

      <div className="card">
        {documents.length === 0 ? (
          <p className="empty">
            No documents are visible to this account. That is a valid result, not an error.
          </p>
        ) : (
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Title</th>
                  <th>Department</th>
                  <th>Access level</th>
                  <th>Pages</th>
                </tr>
              </thead>
              <tbody>
                {documents.map((document) => (
                  <tr key={document.documentId}>
                    <td>{document.title}</td>
                    <td>
                      <span className="tag tag-dept">{document.department}</span>
                    </td>
                    <td>
                      <span className="tag tag-level">{document.accessLevel}</span>
                    </td>
                    <td>{document.pageCount}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </>
  );
}
