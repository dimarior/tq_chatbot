"use client";

import { create } from "zustand";

// El runtime de assistant-ui se monta por "scope". `epoch` es la key de
// <RuntimeScope>: incrementarlo lo remonta con un runtime limpio.
//
// `target` es la intención de navegación del usuario:
//   - undefined -> sin intención: usar el id derivado de la URL (carga
//                  directa, reload, back/forward).
//   - null      -> chat nuevo en blanco.
//   - string    -> abrir ese hilo concreto.
//
// Las navegaciones iniciadas por el usuario (nuevo chat, abrir un hilo,
// archivar el hilo activo) llaman a `open()`, que sube `epoch` y fija
// `target`. La navegación automática /chat -> /chat/{id} que dispara
// ThreadRouteSync tras el primer mensaje NO toca este store: por eso el
// runtime no se remonta y el stream SSE en curso sobrevive.
type RuntimeScopeState = {
  epoch: number;
  target: string | null | undefined;
  open: (threadId: string | null) => void;
};

export const useRuntimeScopeStore = create<RuntimeScopeState>((set) => ({
  epoch: 0,
  target: undefined,
  open: (threadId) => set((s) => ({ epoch: s.epoch + 1, target: threadId })),
}));

export function openRuntimeScope(threadId: string | null) {
  useRuntimeScopeStore.getState().open(threadId);
}

// `target` es un intent de un solo uso. Una vez que la URL coincide con él,
// MyRuntimeProvider lo limpia para que la navegación normal (router.push al
// abrir un hilo) vuelva a mandar sin tocar el epoch (sin remonte).
export function resetRuntimeScopeTarget() {
  if (useRuntimeScopeStore.getState().target !== undefined) {
    useRuntimeScopeStore.setState({ target: undefined });
  }
}

// Resuelve el threadId efectivo del scope: el `target` del store manda; si no
// hay target (undefined) se cae al id derivado de la URL. Lo usan tanto
// MyRuntimeProvider como Thread para mirar siempre el mismo hilo.
export function useResolvedThreadId(
  pathThreadId: string | undefined,
): string | undefined {
  const target = useRuntimeScopeStore((s) => s.target);
  if (target === undefined) return pathThreadId;
  return target ?? undefined;
}
