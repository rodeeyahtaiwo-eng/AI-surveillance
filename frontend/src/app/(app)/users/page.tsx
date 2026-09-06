"use client";

import { Topbar } from "@/components/layout/Topbar";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import { useAuth } from "@/lib/auth-context";

export default function UsersPage() {
  const { user } = useAuth();

  return (
    <div>
      <Topbar title="Users" description="Administrator accounts" />

      <div className="space-y-4 p-6">
        <Card>
          <CardHeader>
            <p className="text-sm font-semibold text-white">Signed-in Administrator</p>
          </CardHeader>
          <CardBody className="grid grid-cols-2 gap-4 text-sm">
            <div>
              <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">Name</p>
              <p className="text-slate-300">{user?.name}</p>
            </div>
            <div>
              <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">Email</p>
              <p className="text-slate-300">{user?.email}</p>
            </div>
            <div>
              <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">Role</p>
              <p className="text-slate-300">{user?.role}</p>
            </div>
          </CardBody>
        </Card>

        <Card>
          <CardBody className="text-sm text-slate-400">
            Multi-admin user management (invite/create/deactivate additional accounts) is not implemented
            yet — this is a single-admin build. Additional administrators can be created with{" "}
            <code className="rounded bg-white/10 px-1 py-0.5 text-xs">backend/prisma/seed.ts</code> or
            directly via Prisma Studio (<code className="rounded bg-white/10 px-1 py-0.5 text-xs">npm run db:studio</code>{" "}
            in backend/) until a real Users CRUD API is built.
          </CardBody>
        </Card>
      </div>
    </div>
  );
}
