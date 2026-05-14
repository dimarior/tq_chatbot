"use client";

import { ThreadPrimitive, useAuiState } from "@assistant-ui/react";
import { useEffect } from "react";

import { usePendingResponseStore } from "@/lib/pendingResponseStore";
import { Composer } from "./Composer";
import { AssistantMessage, UserMessage } from "./Messages";

export function Thread() {
  const isEmpty = useAuiState((s) => s.thread.isEmpty);
  const isRunning = useAuiState((s) => s.thread.isRunning);
  const hasUserMessage = useAuiState((s) =>
    s.thread.messages.some((message) => message.role === "user"),
  );
  const hasAssistantMessage = useAuiState((s) =>
    s.thread.messages.some((message) => message.role === "assistant"),
  );
  const isPendingResponse = usePendingResponseStore((s) => s.isPending);
  const clearPendingResponse = usePendingResponseStore((s) => s.clear);

  useEffect(() => {
    if (hasAssistantMessage || (hasUserMessage && !isRunning)) {
      clearPendingResponse();
    }
  }, [clearPendingResponse, hasAssistantMessage, hasUserMessage, isRunning]);

  return (
    <ThreadPrimitive.Root className="flex h-full flex-col bg-canvas">
      <ThreadPrimitive.Viewport className="flex-1 overflow-y-auto">
        {isEmpty && !isRunning && !isPendingResponse ? (
          <ThreadPrimitive.Empty>
            <EmptyState />
          </ThreadPrimitive.Empty>
        ) : null}

        <div className="mx-auto w-full max-w-3xl px-4 py-6">
          <div className="space-y-6">
            <ThreadPrimitive.Messages
              components={{ UserMessage, AssistantMessage }}
            />
            {isPendingResponse && !hasAssistantMessage ? (
              <PendingAssistantRow />
            ) : null}
          </div>
        </div>
      </ThreadPrimitive.Viewport>

      <div className="border-t border-line/60 bg-canvas">
        <div className="mx-auto w-full max-w-3xl px-4 py-4">
          <Composer />
          <p className="mt-2 text-center text-[11px] text-ink-subtle">
            TQ-Asistente puede equivocarse. Verifica información clínica en
            fuentes oficiales.
          </p>
        </div>
      </div>
    </ThreadPrimitive.Root>
  );
}

function PendingAssistantRow() {
  return (
    <div className="flex gap-3" aria-live="polite">
      <div className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-brand-gradient text-[10px] font-semibold text-white">
        TQ
      </div>
      <div className="inline-flex items-center gap-2 rounded-2xl bg-panel px-3 py-2 text-sm text-ink-muted">
        <span>Escribiendo</span>
        <span className="flex items-center gap-1" aria-hidden="true">
          <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-brand [animation-delay:0ms]" />
          <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-brand [animation-delay:150ms]" />
          <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-brand [animation-delay:300ms]" />
        </span>
      </div>
    </div>
  );
}

function EmptyState() {
  return (
    <div className="flex h-full min-h-[60vh] flex-col items-center justify-center px-4">
      <div className="mb-6 flex h-14 w-14 items-center justify-center rounded-full bg-brand-gradient text-white shadow-[0_8px_24px_rgba(50,63,167,0.25)]">
        <span className="text-base font-semibold tracking-tight">TQ</span>
      </div>
      <h1 className="text-2xl font-semibold tracking-tight text-ink">
        ¿En qué puedo ayudarte hoy?
      </h1>
      <p className="mt-2 max-w-md text-center text-sm text-ink-muted">
        Pregunta sobre Tecnoquímicas S.A. y tqfarma. Las respuestas citan
        fuentes oficiales.
      </p>
    </div>
  );
}
