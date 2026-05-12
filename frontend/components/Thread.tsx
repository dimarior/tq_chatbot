"use client";

import { ThreadPrimitive } from "@assistant-ui/react";

import { Composer } from "./Composer";
import { AssistantMessage, UserMessage } from "./Messages";

export function Thread() {
  return (
    <ThreadPrimitive.Root className="flex h-full flex-col">
      <ThreadPrimitive.Viewport className="flex-1 space-y-3 overflow-y-auto bg-slate-50 px-4 py-4">
        <ThreadPrimitive.Empty>
          <div className="flex h-full items-center justify-center">
            <div className="max-w-md rounded-xl border border-slate-200 bg-white p-6 text-center shadow-sm">
              <p className="text-sm font-semibold text-slate-900">TQ-Asistente</p>
              <p className="mt-2 text-sm text-slate-600">
                Pregunta sobre Tecnoquímicas S.A. y tqfarma. Las respuestas
                citan fuentes oficiales.
              </p>
            </div>
          </div>
        </ThreadPrimitive.Empty>

        <ThreadPrimitive.Messages
          components={{
            UserMessage,
            AssistantMessage,
          }}
        />
      </ThreadPrimitive.Viewport>

      <Composer />
    </ThreadPrimitive.Root>
  );
}
