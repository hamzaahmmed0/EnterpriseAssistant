/**
 * Chat transcript and question input for the Ask surface.
 */

import type { AskResponse } from "@/lib/types";

export interface ChatPanelProps {
  messages: { role: "user" | "assistant"; content: string; response?: AskResponse }[];
  onSubmit: (question: string) => void;
  pending: boolean;
}

export function ChatPanel({ messages, onSubmit, pending }: ChatPanelProps) {
  throw new Error("Not implemented");
}

// TODO:
//  1. Render the transcript, with CitationList under each assistant message.
//  2. Disable the input while pending and show progress; local generation is slow.
//  3. Distinguish an insufficient-evidence answer visually from a normal one.
//  4. Reject an empty question client-side, and let the backend reject it again.
