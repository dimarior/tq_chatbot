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

import { useThreadHistoryAdapter } from "@/lib/threadHistoryAdapter";
import { setReloadThreads, threadListAdapter } from "@/lib/threadListAdapter";
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
  const isRunning = useAuiState((s) => s.thread.isRunning);

  useEffect(() => {
    if (remoteId) {
      const target = threadPath(remoteId);
      if (pathname === "/chat" && isRunning) return;
      if (pathname !== target) router.replace(target);
    }
  }, [isRunning, pathname, remoteId, router]);

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

export function MyRuntimeProvider({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const threadId = useMemo(
    () => parseThreadIdFromPathname(pathname),
    [pathname],
  );
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
