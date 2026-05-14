"use client";

import {
  ExportedMessageRepository,
  type ThreadHistoryAdapter,
} from "@assistant-ui/react";
import { useMemo } from "react";

import { apiUrl } from "./api";
import { flattenContent } from "./messages";
import {
  getActiveRemoteThreadId,
  reloadThreadList,
  setActiveRemoteThreadId,
} from "./threadListAdapter";
import { useSourcesStore } from "./sourcesStore";
import type { ApiMessageRow, Source } from "./types";

const UUID_RE =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

function asUuidOrNull(value: string | null | undefined): string | null {
  if (!value) return null;
  return UUID_RE.test(value) ? value : null;
}

async function jsonFetch<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, init);
  if (!res.ok) throw new Error(`${url} → ${res.status}`);
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

function rehydrateSources(rows: ApiMessageRow[]) {
  const entries: Array<[string, Source[]]> = [];
  for (const row of rows) {
    if (row.role === "assistant" && row.sources && row.sources.length > 0) {
      entries.push([row.id, row.sources]);
    }
  }
  if (entries.length) {
    useSourcesStore.getState().bulkSet(entries);
  }
}

export function useThreadHistoryAdapter(
  routeThreadId: string | undefined,
): ThreadHistoryAdapter {
  return useMemo(
    () => ({
      async load() {
        if (!routeThreadId) {
          setActiveRemoteThreadId(null);
          return ExportedMessageRepository.fromArray([]);
        }

        const remoteId = routeThreadId;
        setActiveRemoteThreadId(remoteId);
        const rows = await jsonFetch<ApiMessageRow[]>(
          apiUrl(`/api/threads/${remoteId}/messages`),
        );
        rehydrateSources(rows);
        return ExportedMessageRepository.fromArray(
          rows.map((row) => ({
            id: row.id,
            role: row.role,
            content: row.content,
            createdAt: new Date(row.created_at),
          })),
        );
      },

      async append({ message, parentId }) {
        if (message.role === "system") return;

        const remoteId = getActiveRemoteThreadId();
        if (!remoteId) {
          throw new Error("No existe un hilo remoto activo para persistir mensajes.");
        }

        const text = flattenContent(message.content);
        const sources =
          message.role === "assistant"
            ? useSourcesStore.getState().byId[message.id] ?? null
            : null;

        await jsonFetch<{ id: string }>(apiUrl(`/api/threads/${remoteId}/messages`), {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            message: {
              id: asUuidOrNull(message.id),
              role: message.role,
              content: text,
              sources,
            },
            parentId: asUuidOrNull(parentId),
          }),
        });

        if (routeThreadId) {
          await reloadThreadList();
        }
      },
    }),
    [routeThreadId],
  );
}
