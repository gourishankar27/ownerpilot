import { Card, CardDescription, CardTitle } from "@ownerpilot/ui";

import { ReorderPlanWorkspace } from "@/components/reorder-plan-workspace";
import { getReorderPlan } from "@/lib/api";

export default async function ReorderPage() {
  const plan = await getReorderPlan(14);

  return (
    <div className="space-y-6">
      <Card className="space-y-3">
        <p className="text-xs font-semibold uppercase tracking-[0.22em] text-[var(--color-brand-600)]">
          Inventory planning
        </p>
        <CardTitle className="text-3xl">Reorder Plan</CardTitle>
        <CardDescription className="max-w-3xl text-base leading-7">
          Convert product, sales, purchase, expiry, and obligation records into a
          cash-aware replenishment plan. This is the next owner workflow after
          imports: what to buy, what to watch, and what to hold.
        </CardDescription>
      </Card>

      <ReorderPlanWorkspace initialPlan={plan} />
    </div>
  );
}
