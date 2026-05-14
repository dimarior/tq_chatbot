"use client";

import {
  AssistantRuntimeProvider,
  useAui,
  useAuiState,
  useLocalRuntime,
  useRemoteThreadListRuntime,
} from "@assistant-ui/react";
import { usePathname, useRouter } from "next/navigation";
import type { ReactNode } from "react";
import { useEffect, useMemo } from "react";

import { usePendingResponseStore } from "@/lib/pendingResponseStore";
import {
  resetRuntimeScopeTarget,
  useResolvedThreadId,
  useRuntimeScopeStore,
} from "@/lib/runtimeScopeStore";
import { useThreadHistoryAdapter } from "@/lib/threadHistoryAdapter";
import {
  setReloadThreads,
  setRouteRemoteThreadId,
  threadListAdapter,
} from "@/lib/threadListAdapter";
import { tqChatAdapter } from "@/lib/tqChatAdapter";

const UUID_RE =
  /[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}/i;
const CHAT_THREAD_PATH_RE = new RegExp(`^/chat/(${UUID_RE.source})$`, "i");

function parseThreadIdFromPathname(pathname: string | null): string | undefined {
  if (!pathname) return undefined;
  const match = CHAT_THREAD_PATH_RE.exec(pathname);
  return match?.[1];
}

function threadPath(threadId: string): string {
  return `/chat/${threadId}`;
}

function ThreadRouteSync() {
  const router = useRouter();
  const pathname = usePathname();
  const remoteId = useAuiState((s) => s.threadListItem.remoteId);
  const isNewChat = usePendingResponseStore((s) => s.isNewChat);

  useEffect(() => {
    // Mientras "Nueva conversación" está activa, el runtime todavía puede
    // arrastrar el remoteId del hilo anterior por un render. Sincronizar la URL
    // en esa ventana nos devolvería al chat viejo, así que esperamos a que el
    // usuario envíe el primer mensaje (begin() limpia isNewChat).
    if (isNewChat) return;
    // Único trabajo de este efecto: promover /chat -> /chat/{id} la primera vez
    // que un chat nuevo crea su hilo remoto. Si la URL YA tiene un id, esa es la
    // fuente de verdad — el runtime se sincroniza por el prop `threadId` de
    // <RuntimeScope>. Reescribir la URL aquí mientras useRemoteThreadListRuntime
    // cambia de hilo de forma asíncrona crea un bucle infinito: el remoteId va
    // por detrás de la URL, lo reescribimos al hilo viejo, el runtime termina de
    // cambiar, lo reescribimos al nuevo, y así sin fin.
    if (pathname !== "/chat") return;
    if (remoteId) {
      router.replace(threadPath(remoteId));
    }
  }, [isNewChat, pathname, remoteId, router]);

  return null;
}

function ThreadListReloadBridge() {
  const aui = useAui();

  useEffect(() => {
    setReloadThreads(() => aui.threads().reload());
    return () => setReloadThreads(null);
  }, [aui]);

  return null;
}

function RuntimeScope({
  children,
  threadId,
}: {
  children: ReactNode;
  threadId: string | undefined;
}) {
  const history = useThreadHistoryAdapter(threadId);
  const runtime = useRemoteThreadListRuntime({
    runtimeHook: () =>
      useLocalRuntime(tqChatAdapter, {
        adapters: { history },
      }),
    adapter: threadListAdapter,
    threadId,
  });

  return (
    <AssistantRuntimeProvider runtime={runtime}>
      <ThreadListReloadBridge />
      <ThreadRouteSync />
      {children}
    </AssistantRuntimeProvider>
  );
}

export function MyRuntimeProvider({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const scopeEpoch = useRuntimeScopeStore((s) => s.epoch);
  const scopeTarget = useRuntimeScopeStore((s) => s.target);
  const pathThreadId = useMemo(
    () => parseThreadIdFromPathname(pathname),
    [pathname],
  );
  const threadId = useResolvedThreadId(pathThreadId);

  useEffect(() => {
    setRouteRemoteThreadId(threadId ?? null);
    return () => setRouteRemoteThreadId(null);
  }, [threadId]);

  useEffect(() => {
    // Cuando la URL ya alcanzó el target, el intent se consumió: lo limpiamos
    // (sin tocar el epoch) para que abrir un hilo con router.push funcione por
    // el cambio del prop threadId, no por un remonte.
    if (scopeTarget === undefined) return;
    const settled =
      scopeTarget === null
        ? pathThreadId === undefined
        : scopeTarget === pathThreadId;
    if (settled) resetRuntimeScopeTarget();
  }, [pathThreadId, scopeTarget]);

  if (pathname === null) {
    return null;
  }

  // La key es el epoch del runtime scope, NO el pathname. Solo remontamos en
  // navegaciones iniciadas por el usuario (que llaman a openRuntimeScope). La
  // navegación automática /chat -> /chat/{id} tras el primer mensaje no toca
  // el epoch, así el stream SSE en curso no se pierde por un remonte.
  return (
    <RuntimeScope key={scopeEpoch} threadId={threadId}>
      {children}
    </RuntimeScope>
  );
}
