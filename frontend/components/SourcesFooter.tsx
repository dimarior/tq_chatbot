"use client";

import { useSourcesStore } from "@/lib/sourcesStore";

export function SourcesFooter({ messageId }: { messageId: string | undefined }) {
  const sources = useSourcesStore((s) => (messageId ? s.byId[messageId] : undefined));
  if (!sources || sources.length === 0) return null;

  return (
    <div className="mt-2 flex flex-wrap gap-1.5 border-t border-slate-100 pt-2">
      <span className="text-[11px] font-medium uppercase tracking-wide text-slate-400">
        Fuentes
      </span>
      {sources.map((s) => (
        <a
          key={s.url}
          href={s.url}
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex max-w-full truncate rounded-full bg-slate-100 px-2 py-0.5 text-[11px] text-slate-700 hover:bg-slate-200"
          title={s.url}
        >
          {s.title || s.url}
        </a>
      ))}
    </div>
  );
}
