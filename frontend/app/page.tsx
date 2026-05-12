import { Thread } from "@/components/Thread";
import { ThreadList } from "@/components/ThreadList";

export default function Page() {
  return (
    <div className="flex h-screen bg-white">
      <aside className="hidden w-72 shrink-0 border-r border-slate-200 bg-slate-50 sm:flex sm:flex-col">
        <div className="border-b border-slate-200 bg-slate-900 px-4 py-4 text-white">
          <p className="text-sm font-semibold">TQ-Asistente</p>
          <p className="text-xs text-slate-300">RAG local · Qwen3-8B</p>
        </div>
        <div className="flex-1 overflow-hidden">
          <ThreadList />
        </div>
      </aside>

      <main className="flex flex-1 flex-col">
        <Thread />
      </main>
    </div>
  );
}
