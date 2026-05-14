"use client";

import {
  ThreadListPrimitive,
  useAui,
  useAuiState,
} from "@assistant-ui/react";
import { useCallback } from "react";
import { useRouter } from "next/navigation";

import { useListedThreadStore } from "@/lib/threadListAdapter";

export function ThreadList() {
  const aui = useAui();
  const router = useRouter();
  const isLoading = useAuiState((s) => s.threads.isLoading);
  const mainThreadId = useAuiState((s) => s.threads.mainThreadId);
  const listedRemoteIds = useListedThreadStore((s) => s.remoteIds);
  const threadItems = useAuiState((s) => s.threads.threadItems);
  const visibleThreadItems = Array.from(
    threadItems
      .filter(
        (item) =>
          item.status === "regular" &&
          !!item.remoteId &&
          listedRemoteIds[item.remoteId] === true,
      )
      .reduce((map, item) => {
        const remoteId = item.remoteId!;
        const current = map.get(remoteId);
        if (!current || scoreThreadItem(item, mainThreadId) >= scoreThreadItem(current, mainThreadId)) {
          map.set(remoteId, item);
        }
        return map;
      }, new Map<string, (typeof threadItems)[number]>()),
  ).map(([, item]) => item);

  const threadCount = visibleThreadItems.length;

  const handleNewChat = useCallback(() => {
    // Mantener `/chat` hasta el primer mensaje evita persistir hilos vacios.
    // router.replace("/chat");
    router.push("/chat");
  }, [router]);

  return (
    <ThreadListPrimitive.Root className="flex h-full flex-col">
      <div className="flex items-center gap-2 px-3 py-3">
        <div className="flex h-7 w-7 items-center justify-center rounded-full bg-brand-gradient text-[10px] font-semibold text-white shadow-[0_2px_6px_rgba(50,63,167,0.2)]">
          TQ
        </div>
        <span className="text-sm font-semibold tracking-tight text-ink">
          TQ-Asistente
        </span>
      </div>

      <div className="px-2 pb-2">
        <ThreadListPrimitive.New
          className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-sm font-medium text-ink hover:bg-panelHover"
          aria-label="Nueva conversación"
          onClick={handleNewChat}
        >
          <NewChatIcon />
          <span>Nueva conversación</span>
        </ThreadListPrimitive.New>
      </div>

      <div className="mt-1 px-2 pb-1 text-[11px] font-medium uppercase tracking-wider text-ink-subtle">
        Recientes
      </div>

      <div className="flex-1 space-y-0.5 overflow-y-auto px-2 pb-3">
        {isLoading ? (
          <ThreadListLoading />
        ) : threadCount > 0 ? (
          visibleThreadItems.map((item) => (
            <ThreadListItem
              key={item.id}
              active={item.id === mainThreadId}
              title={item.title}
              onOpen={() => aui.threads().item({ id: item.id }).switchTo()}
              onArchive={() => aui.threads().item({ id: item.id }).archive()}
            />
          ))
        ) : (
          <div className="px-3 py-3 text-sm text-ink-muted">
            Aun no hay conversaciones guardadas.
          </div>
        )}
      </div>
    </ThreadListPrimitive.Root>
  );
}

function ThreadListLoading() {
  return (
    <div className="space-y-2 px-1 py-2" aria-live="polite" aria-busy="true">
      <p className="px-2 text-xs font-medium text-ink-subtle">
        Cargando conversaciones...
      </p>
      {Array.from({ length: 3 }).map((_, index) => (
        <div
          key={index}
          className="h-9 animate-pulse rounded-lg bg-panelHover"
        />
      ))}
    </div>
  );
}

function ThreadListItem({
  active,
  title,
  onOpen,
  onArchive,
}: {
  active: boolean;
  title: string | undefined;
  onOpen: () => void;
  onArchive: () => void;
}) {
  return (
    <div
      className={`group relative flex items-center rounded-lg text-sm text-ink hover:bg-panelHover ${
        active ? "bg-panelActive text-brand" : ""
      }`}
    >
      <button
        type="button"
        className="flex flex-1 items-center gap-2 truncate px-3 py-2 text-left"
        onClick={onOpen}
      >
        <span className="truncate">{title || "Nueva conversación"}</span>
      </button>
      <button
        type="button"
        className="invisible mr-1 rounded-md p-1.5 text-ink-muted hover:bg-panelActive hover:text-brand group-hover:visible"
        aria-label="Archivar"
        onClick={onArchive}
      >
        <TrashIcon />
      </button>
    </div>
  );
}

function scoreThreadItem(
  item: {
    id: string;
    title?: string | undefined;
  },
  mainThreadId: string,
) {
  const hasRealTitle = !!item.title && item.title !== "Nueva conversación";
  return (hasRealTitle ? 2 : 0) + (item.id === mainThreadId ? 1 : 0);
}

function NewChatIcon() {
  return (
    <svg
      width="18"
      height="18"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="M12 20h9" />
      <path d="M16.5 3.5a2.121 2.121 0 1 1 3 3L7 19l-4 1 1-4 12.5-12.5z" />
    </svg>
  );
}

function TrashIcon() {
  return (
    <svg
      width="14"
      height="14"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="M3 6h18" />
      <path d="M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
      <path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6" />
    </svg>
  );
}
