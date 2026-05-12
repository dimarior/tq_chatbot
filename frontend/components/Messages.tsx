"use client";

import { MessagePrimitive, useMessage } from "@assistant-ui/react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import { SourcesFooter } from "./SourcesFooter";

function MarkdownText({ text }: { text: string }) {
  return (
    <div className="prose prose-sm max-w-none break-words">
      <ReactMarkdown remarkPlugins={[remarkGfm]}>{text || ""}</ReactMarkdown>
    </div>
  );
}

const textComponents = {
  Text: ({ text }: { text: string }) => <MarkdownText text={text} />,
};

export function UserMessage() {
  return (
    <MessagePrimitive.Root className="flex justify-end">
      <div className="max-w-[80%] rounded-2xl rounded-br-sm bg-brand px-3 py-2 text-sm text-white shadow-sm">
        <MessagePrimitive.Content components={textComponents} />
      </div>
    </MessagePrimitive.Root>
  );
}

export function AssistantMessage() {
  const message = useMessage() as { id?: string } | undefined;
  return (
    <MessagePrimitive.Root className="flex justify-start">
      <div className="max-w-[90%] rounded-2xl rounded-bl-sm border border-slate-200 bg-white px-3 py-2 text-sm text-slate-800 shadow-sm">
        <MessagePrimitive.Content components={textComponents} />
        <SourcesFooter messageId={message?.id} />
      </div>
    </MessagePrimitive.Root>
  );
}
