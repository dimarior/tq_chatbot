"use client";

import {
  ExportedMessageRepository,
  RuntimeAdapterProvider,
  useAssistantApi,
  type RemoteThreadListAdapter,
  type ThreadHistoryAdapter,
} from "@assistant-ui/react";
import { createAssistantStream } from "assistant-stream";
import { useMemo } from "react";

import { apiUrl } from "./api";
import { flattenContent } from "./messages";
import { useSourcesStore } from "./sourcesStore";
import type { ApiMessageRow, ApiThread, Source } from "./types";

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
      return {
        threads: data.threads.map((t) => ({
          status: t.archived ? ("archived" as const) : ("regular" as const),
          remoteId: t.id,
          title: t.title,
        })),
      };
    } catch (e) {
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

  unstable_Provider({ children }) {
    const aui = useAssistantApi();
    const history = useMemo<ThreadHistoryAdapter>(
      () => ({
        async load() {
          const remoteId = aui.threadListItem().getState().remoteId;
          if (!remoteId) return { messages: [] };
          const rows = await jsonFetch<ApiMessageRow[]>(
            apiUrl(`/api/threads/${remoteId}/messages`),
          );
          // Re-poblar el sourcesStore: los chips no son parte del content
          // stream, así que sin esto se pierden al recargar el hilo.
          const entries: Array<[string, Source[]]> = [];
          for (const r of rows) {
            if (r.role === "assistant" && r.sources && r.sources.length > 0) {
              entries.push([r.id, r.sources]);
            }
          }
          if (entries.length) useSourcesStore.getState().bulkSet(entries);
          return ExportedMessageRepository.fromArray(
            rows.map((r) => ({
              id: r.id,
              role: r.role,
              content: r.content,
              createdAt: new Date(r.created_at),
            })),
          );
        },
        async append({ message, parentId }) {
          if (message.role === "system") return;
          const { remoteId } = await aui.threadListItem().initialize();
          const text = flattenContent(message.content);
          const sources =
            message.role === "assistant"
              ? useSourcesStore.getState().byId[message.id] ?? null
              : null;
          await jsonFetch<{ id: string }>(
            apiUrl(`/api/threads/${remoteId}/messages`),
            {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({
                message: {
                  id: message.id,
                  role: message.role,
                  content: text,
                  sources,
                },
                parentId: parentId ?? null,
              }),
            },
          );
        },
      }),
      [aui],
    );

    return (
      <RuntimeAdapterProvider adapters={{ history }}>
        {children}
      </RuntimeAdapterProvider>
    );
  },
};
