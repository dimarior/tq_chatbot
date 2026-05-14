"use client";

import { create } from "zustand";

import type { Source } from "./types";

// Map<messageId, Source[]>. Poblado en dos sitios:
//  1. El ChatModelAdapter cuando llega el evento SSE `sources` durante streaming.
//  2. El ThreadHistoryAdapter al hidratar mensajes persistidos.
// Los componentes leen por messageId para renderizar el footer; las fuentes
// no son parte del content stream del modelo, por eso van por canal aparte.
type State = {
  byId: Record<string, Source[]>;
  set: (messageId: string, sources: Source[]) => void;
  bulkSet: (entries: Array<[string, Source[]]>) => void;
};

export const useSourcesStore = create<State>((set) => ({
  byId: {},
  set: (messageId, sources) =>
    set((s) => ({ byId: { ...s.byId, [messageId]: sources } })),
  bulkSet: (entries) =>
    set((s) => {
      const next = { ...s.byId };
      for (const [id, srcs] of entries) next[id] = srcs;
      return { byId: next };
    }),
}));
