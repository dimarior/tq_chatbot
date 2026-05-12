"use client";

import { ThreadPrimitive } from "@assistant-ui/react";

import { Composer } from "./Composer";
import { AssistantMessage, UserMessage } from "./Messages";

export function Thread() {
  return (
    <ThreadPrimitive.Root className="flex h-full flex-col bg-canvas">
      <ThreadPrimitive.Viewport className="flex-1 overflow-y-auto">
        <ThreadPrimitive.Empty>
          <EmptyState />
        </ThreadPrimitive.Empty>

        <div className="mx-auto w-full max-w-3xl px-4 py-6">
          <div className="space-y-6">
            <ThreadPrimitive.Messages
              components={{ UserMessage, AssistantMessage }}
            />
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
