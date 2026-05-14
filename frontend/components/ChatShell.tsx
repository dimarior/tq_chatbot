import { Thread } from "@/components/Thread";
import { ThreadList } from "@/components/ThreadList";

export function ChatShell() {
  return (
    <div className="flex h-screen bg-canvas text-ink">
      <aside className="hidden w-64 shrink-0 bg-panel md:flex md:flex-col">
        <ThreadList />
      </aside>

      <main className="flex flex-1 flex-col">
        <Thread />
      </main>
    </div>
  );
}
