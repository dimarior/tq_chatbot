"use client";

import { MessagePrimitive, useAuiState, useMessage } from "@assistant-ui/react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import { SourcesFooter } from "./SourcesFooter";

function MarkdownText({ text }: { text: string }) {
  return (
    <div className="prose prose-sm max-w-none break-words text-[15px] leading-7 text-ink prose-p:my-2 prose-pre:my-2 prose-headings:font-semibold">
      <ReactMarkdown remarkPlugins={[remarkGfm]}>{text || ""}</ReactMarkdown>
    </div>
  );
}

const textComponents = {
  Text: ({ text }: { text: string }) => <MarkdownText text={text} />,
};

// User: soft grey rounded bubble, right-aligned, max ~70% width — matches ChatGPT.
export function UserMessage() {
  return (
    <MessagePrimitive.Root className="flex justify-end">
      <div className="max-w-[75%] rounded-3xl bg-bubble px-4 py-2.5 text-[15px] leading-6 text-ink">
        <MessagePrimitive.Content components={textComponents} />
      </div>
    </MessagePrimitive.Root>
  );
}

// Assistant: NO bubble, plain text on canvas with a small avatar gutter on the
// left. Sources chips render under the answer.
export function AssistantMessage() {
  const message = useMessage() as unknown as
    | {
        id?: string;
        content?: ReadonlyArray<{ type?: string; text?: string }>;
        status?: { type?: string };
      }
    | undefined;
  const isRunning = useAuiState((s) => s.message.status?.type === "running");
  const hasText = message?.content?.some(
    (part) => part.type === "text" && (part.text?.trim().length ?? 0) > 0,
  );

  return (
    <MessagePrimitive.Root className="flex gap-3">
      <div className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-brand-gradient text-[10px] font-semibold text-white">
        TQ
      </div>
      <div className="min-w-0 flex-1">
        {isRunning && !hasText ? (
          <AssistantLoadingBubble />
        ) : (
          <MessagePrimitive.Content components={textComponents} />
        )}
        <SourcesFooter messageId={message?.id} />
      </div>
    </MessagePrimitive.Root>
  );
}

function AssistantLoadingBubble() {
  return (
    <div
      className="inline-flex items-center gap-2 rounded-2xl bg-panel px-3 py-2 text-sm text-ink-muted"
      aria-live="polite"
      aria-label="TQ-Asistente está escribiendo"
    >
      <span>Escribiendo</span>
      <span className="flex items-center gap-1" aria-hidden="true">
        <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-brand [animation-delay:0ms]" />
        <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-brand [animation-delay:150ms]" />
        <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-brand [animation-delay:300ms]" />
      </span>
    </div>
  );
}
