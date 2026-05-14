"use client";

import { create } from "zustand";

type PendingResponseState = {
  isNewChat: boolean;
  isPending: boolean;
  begin: () => void;
  beginNewChat: () => void;
  clear: () => void;
};

export const usePendingResponseStore = create<PendingResponseState>((set) => ({
  isNewChat: false,
  isPending: false,
  begin: () => set({ isPending: true, isNewChat: false }),
  beginNewChat: () => set({ isPending: false, isNewChat: true }),
  clear: () => set({ isPending: false, isNewChat: false }),
}));
