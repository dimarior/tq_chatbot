"use client";

import { create } from "zustand";

// Store simple para que tqChatAdapter pueda leer el threadId activo
// sin necesidad de refactorizar toda la cadena de adapters.
type State = {
  threadId: string | null;
  setThreadId: (id: string | null) => void;
};

export const useActiveThreadIdStore = create<State>((set) => ({
  threadId: null,
  setThreadId: (id) => set({ threadId: id }),
}));
