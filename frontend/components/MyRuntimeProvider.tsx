"use client";

import {
  AssistantRuntimeProvider,
  unstable_useRemoteThreadListRuntime,
  useLocalRuntime,
} from "@assistant-ui/react";
import type { ReactNode } from "react";

import { threadListAdapter } from "@/lib/threadListAdapter";
import { tqChatAdapter } from "@/lib/tqChatAdapter";

export function MyRuntimeProvider({ children }: { children: ReactNode }) {
  const runtime = unstable_useRemoteThreadListRuntime({
    runtimeHook: () => useLocalRuntime(tqChatAdapter),
    adapter: threadListAdapter,
  });
  return (
    <AssistantRuntimeProvider runtime={runtime}>
      {children}
    </AssistantRuntimeProvider>
  );
}
