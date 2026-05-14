"use client";

import { create } from "zustand";

// Qué hilo está hidratando su historial desde el API ahora mismo. Lo escribe
// ThreadHistoryAdapter.load() (begin al empezar el fetch, end en el finally) y
// lo lee Thread.tsx para mostrar el estado de carga al conmutar de hilo.
//
// No basta con `s.thread.isEmpty` ni con `activeRemoteId`: el runtime de
// assistant-ui reporta el hilo recién conmutado como no-vacío y con el
// remoteId ya actualizado ANTES de que `load()` resuelva, así que esos dos
// señalan "listo" mientras el historial todavía viaja por la red.
type ThreadHydrationState = {
  hydratingThreadId: string | null;
  beginHydration: (threadId: string) => void;
  endHydration: (threadId: string) => void;
};

export const useThreadHydrationStore = create<ThreadHydrationState>((set) => ({
  hydratingThreadId: null,
  beginHydration: (threadId) => set({ hydratingThreadId: threadId }),
  // Sólo limpiamos si el id coincide: si una carga vieja termina después de que
  // ya empezó otra, no debe apagar el indicador de la carga en curso.
  endHydration: (threadId) =>
    set((s) =>
      s.hydratingThreadId === threadId ? { hydratingThreadId: null } : s,
    ),
}));
