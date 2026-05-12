"use client";

import { ComposerPrimitive } from "@assistant-ui/react";

export function Composer() {
  return (
    <ComposerPrimitive.Root className="relative flex items-end gap-2 rounded-3xl border border-line/70 bg-canvas px-4 py-3 shadow-composer focus-within:border-brand/40 focus-within:ring-2 focus-within:ring-brand/10">
      <ComposerPrimitive.Input
        rows={1}
        autoFocus
        placeholder="Pregunta sobre Tecnoquímicas..."
        className="max-h-48 flex-1 resize-none bg-transparent text-[15px] leading-6 text-ink placeholder:text-ink-subtle focus:outline-none"
      />
      <ComposerPrimitive.Send
        className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-brand-gradient text-white shadow-[0_4px_12px_rgba(50,63,167,0.25)] transition hover:opacity-90 disabled:cursor-not-allowed disabled:bg-line disabled:bg-none disabled:text-ink-subtle disabled:shadow-none"
        aria-label="Enviar"
      >
        <ArrowUpIcon />
      </ComposerPrimitive.Send>
    </ComposerPrimitive.Root>
  );
}

function ArrowUpIcon() {
  return (
    <svg
      width="16"
      height="16"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2.2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="M12 19V5" />
      <path d="M5 12l7-7 7 7" />
    </svg>
  );
}
