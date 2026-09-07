/**
 * Ask: chat over the document corpus, scoped to the signed-in user.
 */

export default function AskPage() {
  throw new Error("Not implemented");
}

// TODO:
//  1. Server-side: read the session, redirect if absent.
//  2. Render ChatPanel and wire submission to lib/api.ask through a server action.
//  3. Render the insufficient-evidence answer as a first-class result with its own styling --
//     it is the honest outcome, not an error toast.
//  4. Show evidence score and attempt count somewhere visible; the adaptive loop is a
//     contribution and the demo should make it observable.
