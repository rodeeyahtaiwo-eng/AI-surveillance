import { Sidebar } from "@/components/layout/Sidebar";
import { RequireAuth } from "@/components/layout/RequireAuth";

export default function AppLayout({ children }: { children: React.ReactNode }) {
  return (
    <RequireAuth>
      <div className="flex">
        <Sidebar />
        <main className="min-h-screen flex-1 overflow-x-hidden">{children}</main>
      </div>
    </RequireAuth>
  );
}
