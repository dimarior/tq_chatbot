"use client";

import { create } from "zustand";

type State = {
  temperature: number;
  topK: number;
  setTemperature: (v: number) => void;
  setTopK: (v: number) => void;
};

export const useSettingsStore = create<State>((set) => ({
  temperature: 0.2,
  topK: 6,
  setTemperature: (v) => set({ temperature: v }),
  setTopK: (v) => set({ topK: v }),
}));
