"use client";

import { ComposerPrimitive } from "@assistant-ui/react";

export function Composer() {
  return (
    <ComposerPrimitive.Root className="flex items-end gap-2 border-t border-slate-200 bg-white px-3 py-3">
      <ComposerPrimitive.Input
        rows={1}
        autoFocus
        placeholder="Pregunta sobre Tecnoquímicas..."
        className="flex-1 resize-none rounded-lg border border-slate-300 px-3 py-2 text-sm placeholder:text-slate-400 focus:border-brand focus:outline-none focus:ring-1 focus:ring-brand"
      />
      <ComposerPrimitive.Send className="rounded-lg bg-brand px-3 py-2 text-sm font-medium text-white hover:bg-brand-dark disabled:cursor-not-allowed disabled:bg-slate-300">
        Enviar
      </ComposerPrimitive.Send>
    </ComposerPrimitive.Root>
  );
}
