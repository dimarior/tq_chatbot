"use client";

import {
  ThreadListItemPrimitive,
  ThreadListPrimitive,
} from "@assistant-ui/react";

export function ThreadList() {
  return (
    <ThreadListPrimitive.Root className="flex h-full flex-col">
      <div className="border-b border-slate-200 p-3">
        <ThreadListPrimitive.New className="flex w-full items-center justify-center gap-2 rounded-lg bg-brand px-3 py-2 text-sm font-medium text-white hover:bg-brand-dark">
          <span className="text-base leading-none">+</span> Nueva conversación
        </ThreadListPrimitive.New>
      </div>

      <div className="flex-1 space-y-1 overflow-y-auto p-2">
        <ThreadListPrimitive.Items
          components={{ ThreadListItem: ThreadListItem }}
        />
      </div>
    </ThreadListPrimitive.Root>
  );
}

function ThreadListItem() {
  return (
    <ThreadListItemPrimitive.Root className="group flex items-center gap-1 rounded-md text-sm text-slate-700 hover:bg-slate-100 data-[active]:bg-blue-50 data-[active]:text-brand">
      <ThreadListItemPrimitive.Trigger className="flex-1 truncate px-3 py-2 text-left">
        <ThreadListItemPrimitive.Title fallback="Nueva conversación" />
      </ThreadListItemPrimitive.Trigger>
      <ThreadListItemPrimitive.Archive
        className="invisible mr-1 rounded p-1 text-slate-400 hover:bg-slate-200 hover:text-slate-700 group-hover:visible"
        aria-label="Archivar"
      >
        ✕
      </ThreadListItemPrimitive.Archive>
    </ThreadListItemPrimitive.Root>
  );
}
