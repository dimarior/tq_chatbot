"use client";

import { create } from "zustand";

type PendingResponseState = {
  isPending: boolean;
  begin: () => void;
  clear: () => void;
};

export const usePendingResponseStore = create<PendingResponseState>((set) => ({
  isPending: false,
  begin: () => set({ isPending: true }),
  clear: () => set({ isPending: false }),
}));
