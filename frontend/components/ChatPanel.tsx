"use client";

/**
 * Chat transcript and question input for the Ask surface.
 *
 * Two things this renders that a normal chat UI would not: the insufficient-evidence answer gets
 * its own treatment rather than being hidden as an error, and the evidence score and attempt
 * count are shown -- the adaptive loop is a contribution, so the demo should make it observable.
 */

import { useActionState } from "react";

import { askAction, type AskState } from "@/app/actions";
import { CitationList } from "@/components/CitationList";

const EMPTY: AskState = { turns: [] };

export function ChatPanel() {
  const [state, formAction, pending] = useActionState<AskState, FormData>(askAction, EMPTY);

  return (
    <>
      <div className="card">
        {state.turns.length === 0 && !pending ? (
          <p className="empty">Ask a question about your company documents.</p>
        ) : null}

        {state.turns.map((turn, index) => (
          <div
            key={index}
            className={`turn${turn.result && !turn.result.sufficient ? " insufficient" : ""}`}
          >
            <div className="who">{turn.role === "user" ? "You" : "Assistant"}</div>
            <div className="body">{turn.content}</div>

            {turn.result ? (
              <>
                <CitationList
                  citations={turn.result.citations}
                  sufficient={turn.result.sufficient}
                />
                <div className="meta">
                  <span>evidence {turn.result.evidenceScore.toFixed(2)}</span>
                  <span>
                    {turn.result.attempts} attempt{turn.result.attempts === 1 ? "" : "s"}
                  </span>
                  <span>{turn.result.latencySeconds.toFixed(1)}s</span>
                </div>
              </>
            ) : null}
          </div>
        ))}

        {pending ? <p className="pending">Retrieving and generating… this is a local model, so give it a moment.</p> : null}
      </div>

      {state.error ? <p className="error">{state.error}</p> : null}

      <form action={formAction} className="card">
        <div className="field">
          <label htmlFor="question">Your question</label>
          <textarea
            id="question"
            name="question"
            rows={3}
            required
            placeholder="How many days of paid annual leave do I accrue?"
            disabled={pending}
          />
        </div>
        <button type="submit" disabled={pending}>
          {pending ? "Working…" : "Ask"}
        </button>
      </form>
    </>
  );
}
