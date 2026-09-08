import { Sidebar } from "@/components/layout/Sidebar";
import { RequireAuth } from "@/components/layout/RequireAuth";

export default function AppLayout({ children }: { children: React.ReactNode }) {
  return (
    <RequireAuth>
      {/* Fixes the sidebar scrolling away with the page: the outer row is pinned to
          exactly the viewport height with its own overflow hidden, so the browser's
          document/body never scrolls; <main> becomes the one independent scroll
          container instead. Sidebar's own <aside className="h-screen ..."> now fills
          this already-100vh parent exactly, so it stays visibly fixed in place. */}
      <div className="flex h-screen overflow-hidden">
        <Sidebar />
        <main className="flex-1 overflow-y-auto overflow-x-hidden">{children}</main>
      </div>
    </RequireAuth>
  );
}
