"use client";

import type { ChatModelAdapter } from "@assistant-ui/react";

import { apiUrl } from "./api";
import { flattenContent, type Role } from "./messages";
import { parseSSE } from "./sse";
import { useSettingsStore } from "./settingsStore";
import { useSourcesStore } from "./sourcesStore";
import { getActiveRemoteThreadId } from "./threadListAdapter";
import type { Source } from "./types";

type WireMessage = { role: Role; content: string };

function toWire(m: any): WireMessage | null {
  const role = m?.role;
  if (role !== "user" && role !== "assistant") return null;
  const text = flattenContent(m?.content);
  if (!text) return null;
  return { role, content: text };
}

export const tqChatAdapter: ChatModelAdapter = {
  async *run(opts: any) {
    const messages: any[] = opts.messages ?? [];
    const abortSignal: AbortSignal | undefined = opts.abortSignal;
    const assistantId: string | undefined =
      opts.unstable_assistantMessageId ?? opts.assistantMessageId;

    const last = messages[messages.length - 1];
    const question = flattenContent(last?.content).trim();
    if (!question) throw new Error("Pregunta vacía");

    const history: WireMessage[] = [];
    for (const m of messages.slice(0, -1)) {
      const wire = toWire(m);
      if (wire) history.push(wire);
    }

    // threadListAdapter ya mantiene este valor sincronizado en initialize/fetch;
    // no duplicar el estado con un zustand store paralelo.
    const threadId = getActiveRemoteThreadId();
    const { temperature, topK } = useSettingsStore.getState();

    const res = await fetch(apiUrl("/api/chat"), {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Accept: "text/event-stream",
      },
      body: JSON.stringify({ question, history, thread_id: threadId, temperature, top_k: topK }),
      signal: abortSignal,
    });

    if (!res.ok || !res.body) {
      throw new Error(`Chat falló (${res.status})`);
    }

    let acc = "";
    for await (const frame of parseSSE(res.body)) {
      if (frame.event === "sources") {
        if (assistantId) {
          try {
            const parsed = JSON.parse(frame.data) as Source[];
            useSourcesStore.getState().set(assistantId, parsed);
          } catch {
            // payload corrupto: ignorar para no tumbar el stream
          }
        }
      } else if (frame.event === "token") {
        acc += frame.data;
        // Contrato del LocalRuntime: cada yield reemplaza el contenido,
        // así que emitimos el acumulado, no deltas.
        yield { content: [{ type: "text", text: acc }] };
      } else if (frame.event === "done") {
        break;
      } else if (frame.event === "error") {
        let msg = "Hubo un problema al procesar tu pregunta.";
        try {
          const obj = JSON.parse(frame.data) as { error?: string; detail?: string };
          if (obj.error) msg = obj.error;
          if (obj.detail) msg = `${msg} (${obj.detail})`;
        } catch {
          /* noop */
        }
        throw new Error(msg);
      }
    }
  },
};
