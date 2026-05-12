"use client";

import {
  ThreadListItemPrimitive,
  ThreadListPrimitive,
} from "@assistant-ui/react";

export function ThreadList() {
  return (
    <ThreadListPrimitive.Root className="flex h-full flex-col">
      <div className="flex items-center justify-between px-3 py-3">
        <span className="text-sm font-semibold tracking-tight text-ink">
          TQ-Asistente
        </span>
      </div>

      <div className="px-2 pb-2">
        <ThreadListPrimitive.New
          className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-sm font-medium text-ink hover:bg-panelHover"
          aria-label="Nueva conversación"
        >
          <NewChatIcon />
          <span>Nueva conversación</span>
        </ThreadListPrimitive.New>
      </div>

      <div className="mt-1 px-2 pb-1 text-[11px] font-medium uppercase tracking-wider text-ink-subtle">
        Recientes
      </div>

      <div className="flex-1 space-y-0.5 overflow-y-auto px-2 pb-3">
        <ThreadListPrimitive.Items components={{ ThreadListItem }} />
      </div>
    </ThreadListPrimitive.Root>
  );
}

function ThreadListItem() {
  return (
    <ThreadListItemPrimitive.Root className="group relative flex items-center rounded-lg text-sm text-ink hover:bg-panelHover data-[active]:bg-panelActive">
      <ThreadListItemPrimitive.Trigger className="flex flex-1 items-center gap-2 truncate px-3 py-2 text-left">
        <ThreadListItemPrimitive.Title fallback="Nueva conversación" />
      </ThreadListItemPrimitive.Trigger>
      <ThreadListItemPrimitive.Archive
        className="invisible mr-1 rounded-md p-1.5 text-ink-muted hover:bg-panelActive hover:text-ink group-hover:visible"
        aria-label="Archivar"
      >
        <TrashIcon />
      </ThreadListItemPrimitive.Archive>
    </ThreadListItemPrimitive.Root>
  );
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
