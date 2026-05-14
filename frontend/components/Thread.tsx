"use client";

import { ThreadPrimitive, useAuiState } from "@assistant-ui/react";
import { usePathname } from "next/navigation";
import { useEffect } from "react";

import { usePendingResponseStore } from "@/lib/pendingResponseStore";
import { useResolvedThreadId } from "@/lib/runtimeScopeStore";
import { useThreadHydrationStore } from "@/lib/threadHydrationStore";
import { Composer } from "./Composer";
import { AssistantMessage, UserMessage } from "./Messages";

const UUID_RE =
  /[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}/i;
const CHAT_THREAD_PATH_RE = new RegExp(`^/chat/(${UUID_RE.source})$`, "i");

function parseThreadIdFromPathname(pathname: string | null): string | undefined {
  if (!pathname) return undefined;
  const match = CHAT_THREAD_PATH_RE.exec(pathname);
  return match?.[1];
}

export function Thread() {
  const pathname = usePathname();
  // Resolvemos el hilo igual que MyRuntimeProvider: la intención del store
  // manda sobre la URL, así no hay desajuste durante la navegación async.
  const routeThreadId = useResolvedThreadId(parseThreadIdFromPathname(pathname));
  const isRunning = useAuiState((s) => s.thread.isRunning);
  const activeRemoteId = useAuiState((s) => s.threadListItem.remoteId);
  const hydratingThreadId = useThreadHydrationStore((s) => s.hydratingThreadId);
  const hasUserMessage = useAuiState((s) =>
    s.thread.messages.some((message) => message.role === "user"),
  );
  const hasAssistantMessage = useAuiState((s) =>
    s.thread.messages.some((message) => message.role === "assistant"),
  );
  const isNewChat = usePendingResponseStore((s) => s.isNewChat);
  const isPendingResponse = usePendingResponseStore((s) => s.isPending);
  const clearPendingResponse = usePendingResponseStore((s) => s.clear);

  useEffect(() => {
    if (isRunning || (!isNewChat && (hasAssistantMessage || hasUserMessage))) {
      clearPendingResponse();
    }
  }, [
    clearPendingResponse,
    hasAssistantMessage,
    hasUserMessage,
    isNewChat,
    isRunning,
  ]);

  // El historial está cargando si el adapter marcó este hilo como hidratando,
  // o si el runtime aún no ha conmutado su remoteId al hilo de la URL (la
  // ventana previa a que load() arranque). `s.thread.isEmpty` NO sirve aquí:
  // el runtime reporta el hilo recién conmutado como no-vacío antes de que el
  // fetch termine.
  const isHydratingPersistedThread =
    !isNewChat &&
    !!routeThreadId &&
    !isRunning &&
    (hydratingThreadId === routeThreadId || activeRemoteId !== routeThreadId);
  const showWelcomeState =
    !routeThreadId &&
    !isRunning &&
    (isNewChat || (!isPendingResponse && !hasUserMessage && !hasAssistantMessage));

  return (
    <ThreadPrimitive.Root className="flex h-full flex-col bg-canvas">
      <ThreadPrimitive.Viewport className="flex-1 overflow-y-auto">
        {isHydratingPersistedThread ? (
          <LoadingThreadState />
        ) : showWelcomeState ? (
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

function LoadingThreadState() {
  return (
    <div
      className="flex h-full min-h-[60vh] flex-col items-center justify-center px-4"
      aria-live="polite"
      data-testid="thread-loading-state"
    >
      <div className="mb-4 flex h-12 w-12 items-center justify-center rounded-full bg-brand-gradient text-white shadow-[0_8px_24px_rgba(50,63,167,0.25)]">
        <span className="text-sm font-semibold tracking-tight">TQ</span>
      </div>
      <p className="text-sm font-medium text-ink">Cargando conversación...</p>
    </div>
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
