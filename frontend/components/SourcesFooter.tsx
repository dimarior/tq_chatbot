"use client";

import { useSourcesStore } from "@/lib/sourcesStore";

export function SourcesFooter({ messageId }: { messageId: string | undefined }) {
  const sources = useSourcesStore((s) => (messageId ? s.byId[messageId] : undefined));
  if (!sources || sources.length === 0) return null;

  return (
    <div className="mt-3 flex flex-wrap items-center gap-1.5">
      <span className="text-[11px] font-medium uppercase tracking-wider text-ink-subtle">
        Fuentes
      </span>
      {sources.map((s) => (
        <a
          key={s.url}
          href={s.url}
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex max-w-[14rem] items-center gap-1 truncate rounded-full border border-line bg-panel px-2.5 py-0.5 text-[12px] text-ink-muted transition hover:border-brand/30 hover:bg-panelHover hover:text-brand"
          title={s.url}
        >
          <LinkIcon />
          <span className="truncate">{s.title || s.url}</span>
        </a>
      ))}
    </div>
  );
}

function LinkIcon() {
  return (
    <svg
      width="11"
      height="11"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      className="shrink-0"
    >
      <path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71" />
      <path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71" />
    </svg>
  );
}
