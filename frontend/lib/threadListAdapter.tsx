"use client";

import {
  ExportedMessageRepository,
  type RemoteThreadListAdapter,
} from "@assistant-ui/react";
import { createAssistantStream } from "assistant-stream";
import { create } from "zustand";

import { apiUrl } from "./api";
import { flattenContent } from "./messages";
import type { ApiThread } from "./types";

const UUID_RE =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

let activeRemoteThreadId: string | null = null;
let reloadThreads: () => Promise<void> = async () => {};

type ListedThreadState = {
  remoteIds: Record<string, true>;
  setRemoteIds: (ids: string[]) => void;
};

export const useListedThreadStore = create<ListedThreadState>((set) => ({
  remoteIds: {},
  setRemoteIds: (ids) =>
    set({
      remoteIds: Object.fromEntries(ids.map((id) => [id, true] as const)),
    }),
}));

export function setActiveRemoteThreadId(threadId: string | null) {
  activeRemoteThreadId = threadId;
}

export function getActiveRemoteThreadId() {
  return activeRemoteThreadId;
}

export function setReloadThreads(fn: (() => Promise<void>) | null) {
  reloadThreads = fn ?? (async () => {});
}

export async function reloadThreadList() {
  await reloadThreads().catch(() => undefined);
}

async function jsonFetch<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, init);
  if (!res.ok) throw new Error(`${url} → ${res.status}`);
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

async function patchThread(remoteId: string, body: Record<string, unknown>) {
  await jsonFetch<void>(apiUrl(`/api/threads/${remoteId}`), {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

export const threadListAdapter: RemoteThreadListAdapter = {
  async list() {
    // `list()` corre al montar el RuntimeProvider; si el API está caído no
    // tumbamos toda la UI — el chat sigue siendo usable, sólo se pierde la
    // hidratación del sidebar.
    try {
      const data = await jsonFetch<{ threads: ApiThread[] }>(apiUrl("/api/threads"));
      useListedThreadStore
        .getState()
        .setRemoteIds(data.threads.map((thread) => thread.id));
      return {
        threads: data.threads.map((t) => ({
          status: t.archived ? ("archived" as const) : ("regular" as const),
          remoteId: t.id,
          title: t.title,
        })),
      };
    } catch (e) {
      useListedThreadStore.getState().setRemoteIds([]);
      console.warn("[threadListAdapter.list] fallo cargando hilos:", e);
      return { threads: [] };
    }
  },

  async initialize(threadId: string) {
    const created = await jsonFetch<ApiThread>(apiUrl("/api/threads"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ localId: threadId }),
    });
    setActiveRemoteThreadId(created.id);
    return { remoteId: created.id, externalId: undefined };
  },

  async rename(remoteId, title) {
    await patchThread(remoteId, { title });
  },

  async archive(remoteId) {
    await patchThread(remoteId, { archived: true });
  },

  async unarchive(remoteId) {
    await patchThread(remoteId, { archived: false });
  },

  async delete(remoteId) {
    await jsonFetch<void>(apiUrl(`/api/threads/${remoteId}`), {
      method: "DELETE",
    });
  },

  async fetch(remoteId) {
    const t = await jsonFetch<ApiThread>(apiUrl(`/api/threads/${remoteId}`));
    setActiveRemoteThreadId(t.id);
    return {
      status: t.archived ? ("archived" as const) : ("regular" as const),
      remoteId: t.id,
      title: t.title,
    };
  },

  async generateTitle(remoteId, messages) {
    return createAssistantStream(async (controller) => {
      // El título es accesorio: si Ollama está caído o el endpoint falla,
      // dejamos el título por defecto en lugar de tumbar la UI.
      try {
        const wire = messages.map((m) => ({
          role: m.role,
          content: flattenContent(m.content),
        }));
        const { title } = await jsonFetch<{ title: string }>(
          apiUrl(`/api/threads/${remoteId}/title`),
          {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ messages: wire }),
          },
        );
        controller.appendText(title);
      } catch (e) {
        console.warn("[threadListAdapter.generateTitle] fallo:", e);
      }
    });
  },
};
