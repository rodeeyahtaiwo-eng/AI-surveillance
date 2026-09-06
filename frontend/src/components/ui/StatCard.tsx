import type { LucideIcon } from "lucide-react";
import { Card, CardBody } from "./Card";
import clsx from "clsx";

export function StatCard({
  label,
  value,
  icon: Icon,
  tone = "default",
  hint,
}: {
  label: string;
  value: string | number;
  icon: LucideIcon;
  tone?: "default" | "danger" | "warning" | "success";
  hint?: string;
}) {
  const toneStyles = {
    default: "text-slate-300 bg-white/5",
    danger: "text-severity-critical bg-severity-critical/10",
    warning: "text-severity-medium bg-severity-medium/10",
    success: "text-severity-low bg-severity-low/10",
  }[tone];

  return (
    <Card>
      <CardBody className="flex items-start justify-between">
        <div>
          <p className="text-xs font-medium uppercase tracking-wide text-slate-400">{label}</p>
          <p className="mt-2 text-2xl font-semibold text-white">{value}</p>
          {hint && <p className="mt-1 text-xs text-slate-500">{hint}</p>}
        </div>
        <div className={clsx("rounded-md p-2", toneStyles)}>
          <Icon className="h-5 w-5" />
        </div>
      </CardBody>
    </Card>
  );
}
