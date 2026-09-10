/**
 * Ask: chat over the document corpus, scoped to the signed-in user.
 */

import { ChatPanel } from "@/components/ChatPanel";
import { requireSession } from "@/lib/session";

export default async function AskPage() {
  const { identity } = await requireSession();

  return (
    <>
      <h1>Ask</h1>
      <p className="lede">
        Answers are drawn only from documents {identity.name} is authorised to read, and every
        answer is cited. When the evidence is not enough, the assistant says so instead of
        guessing.
      </p>
      <ChatPanel />
    </>
  );
}
