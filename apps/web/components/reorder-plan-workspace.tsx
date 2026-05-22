"use client";

import { useState, useTransition } from "react";

import type { ReorderPlanItem, ReorderPlanResult } from "@ownerpilot/contracts";
import { Button, Card, CardDescription, CardTitle } from "@ownerpilot/ui";

import { getReorderPlan } from "@/lib/api";

const currency = new Intl.NumberFormat("en-IN", {
  currency: "INR",
  maximumFractionDigits: 0,
  style: "currency",
});

const horizons = [7, 14, 30, 45];

function toneForPriority(priority: ReorderPlanItem["priority"]) {
  switch (priority) {
    case "critical":
      return "bg-rose-100 text-rose-700 dark:bg-rose-500/15 dark:text-rose-200";
    case "watch":
      return "bg-amber-100 text-amber-700 dark:bg-amber-500/15 dark:text-amber-200";
    default:
      return "bg-slate-100 text-slate-700 dark:bg-white/10 dark:text-slate-200";
  }
}

function toneForExpiry(risk: ReorderPlanItem["expiryRisk"]) {
  switch (risk) {
    case "high":
      return "text-rose-600 dark:text-rose-300";
    case "medium":
      return "text-amber-600 dark:text-amber-300";
    default:
      return "text-slate-500 dark:text-slate-400";
  }
}

function formatCover(days: number) {
  if (days >= 999) {
    return "99+ days";
  }

  return `${days.toFixed(1)} days`;
}

export function ReorderPlanWorkspace({
  initialPlan,
}: {
  initialPlan: ReorderPlanResult;
}) {
  const [plan, setPlan] = useState(initialPlan);
  const [selectedHorizon, setSelectedHorizon] = useState(initialPlan.horizonDays);
  const [isPending, startTransition] = useTransition();
  const [isLoading, setIsLoading] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  function handleHorizonChange(horizonDays: number) {
    setSelectedHorizon(horizonDays);
    setIsLoading(true);
    setMessage(null);
    startTransition(() => {
      void getReorderPlan(horizonDays)
        .then((nextPlan) => {
          setPlan(nextPlan);
          setMessage(`Updated reorder plan for ${nextPlan.horizonDays} days.`);
        })
        .catch(() => {
          setMessage("Could not refresh the reorder plan right now.");
        })
        .finally(() => {
          setIsLoading(false);
        });
    });
  }

  const costOverBudget = plan.totalRecommendedCostInr > plan.cashAwareBudgetInr;

  return (
    <div className="space-y-6">
      <section className="grid gap-5 lg:grid-cols-[1fr_0.75fr]">
        <Card className="space-y-4">
          <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
            <div>
              <CardTitle className="text-2xl">{plan.headline}</CardTitle>
              <CardDescription className="mt-2 leading-7">
                Generated {plan.generatedAt.slice(0, 19).replace("T", " ")}. The
                plan blends sales velocity, stock on hand, supplier cost, expiry
                risk, and near-term cash pressure.
              </CardDescription>
            </div>
            <div className="flex flex-wrap gap-2">
              {horizons.map((horizon) => (
                <Button
                  className="h-9 px-4 text-xs"
                  disabled={isLoading || isPending || selectedHorizon === horizon}
                  key={horizon}
                  onClick={() => handleHorizonChange(horizon)}
                  variant={selectedHorizon === horizon ? "primary" : "ghost"}
                >
                  {horizon}d
                </Button>
              ))}
            </div>
          </div>

          <div className="grid gap-3 md:grid-cols-3">
            <div className="rounded-2xl bg-slate-100 px-4 py-3 dark:bg-white/5">
              <p className="text-xs uppercase tracking-[0.18em] text-slate-500">
                Cash-aware budget
              </p>
              <p className="mt-2 text-xl font-semibold">
                {currency.format(plan.cashAwareBudgetInr)}
              </p>
            </div>
            <div className="rounded-2xl bg-slate-100 px-4 py-3 dark:bg-white/5">
              <p className="text-xs uppercase tracking-[0.18em] text-slate-500">
                Recommended cost
              </p>
              <p
                className={`mt-2 text-xl font-semibold ${
                  costOverBudget
                    ? "text-rose-600 dark:text-rose-300"
                    : "text-emerald-600 dark:text-emerald-300"
                }`}
              >
                {currency.format(plan.totalRecommendedCostInr)}
              </p>
            </div>
            <div className="rounded-2xl bg-slate-100 px-4 py-3 dark:bg-white/5">
              <p className="text-xs uppercase tracking-[0.18em] text-slate-500">
                Items reviewed
              </p>
              <p className="mt-2 text-xl font-semibold">{plan.items.length}</p>
            </div>
          </div>

          {message ? (
            <p className="rounded-2xl bg-[var(--color-brand-50)] px-4 py-3 text-sm font-medium text-[var(--color-brand-700)] dark:bg-[var(--color-brand-600)]/10 dark:text-[var(--color-brand-200)]">
              {message}
            </p>
          ) : null}
        </Card>

        <Card className="space-y-4">
          <CardTitle>Owner recommendations</CardTitle>
          <ul className="space-y-3 text-sm leading-7 text-slate-600 dark:text-slate-300">
            {plan.recommendations.map((recommendation: string) => (
              <li
                className="rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 dark:border-white/10 dark:bg-white/5"
                key={recommendation}
              >
                {recommendation}
              </li>
            ))}
          </ul>
        </Card>
      </section>

      <section className="grid gap-4 xl:grid-cols-2">
        {plan.items.map((item: ReorderPlanItem) => (
          <Card className="space-y-4" key={item.sku}>
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <p className="text-xs font-semibold uppercase tracking-[0.2em] text-[var(--color-brand-600)]">
                  {item.sku} • {item.category}
                </p>
                <CardTitle className="mt-2 text-2xl">{item.name}</CardTitle>
                {item.supplierName ? (
                  <CardDescription className="mt-2">
                    Preferred supplier signal: {item.supplierName}
                  </CardDescription>
                ) : null}
              </div>
              <span
                className={`rounded-full px-3 py-1 text-xs font-semibold uppercase tracking-[0.18em] ${toneForPriority(
                  item.priority,
                )}`}
              >
                {item.priority}
              </span>
            </div>

            <div className="grid gap-3 md:grid-cols-4">
              <div className="rounded-2xl bg-slate-100 px-4 py-3 dark:bg-white/5">
                <p className="text-xs uppercase tracking-[0.18em] text-slate-500">
                  Stock
                </p>
                <p className="mt-2 font-semibold">{item.currentStock}</p>
              </div>
              <div className="rounded-2xl bg-slate-100 px-4 py-3 dark:bg-white/5">
                <p className="text-xs uppercase tracking-[0.18em] text-slate-500">
                  Velocity
                </p>
                <p className="mt-2 font-semibold">{item.avgDailySales}/day</p>
              </div>
              <div className="rounded-2xl bg-slate-100 px-4 py-3 dark:bg-white/5">
                <p className="text-xs uppercase tracking-[0.18em] text-slate-500">
                  Cover
                </p>
                <p className="mt-2 font-semibold">
                  {formatCover(item.daysOfCover)}
                </p>
              </div>
              <div className="rounded-2xl bg-slate-100 px-4 py-3 dark:bg-white/5">
                <p className="text-xs uppercase tracking-[0.18em] text-slate-500">
                  Expiry
                </p>
                <p className={`mt-2 font-semibold ${toneForExpiry(item.expiryRisk)}`}>
                  {item.expiryRisk}
                </p>
              </div>
            </div>

            <div className="rounded-[24px] border border-dashed border-slate-300 bg-white/80 p-4 dark:border-white/15 dark:bg-white/5">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <p className="text-sm font-medium">Recommended reorder</p>
                  <p className="mt-1 text-3xl font-semibold">
                    {item.recommendedReorderQty} units
                  </p>
                </div>
                <p className="text-lg font-semibold">
                  {currency.format(item.estimatedReorderCostInr)}
                </p>
              </div>
              <p className="mt-3 text-sm leading-7 text-slate-600 dark:text-slate-300">
                {item.rationale}
              </p>
            </div>
          </Card>
        ))}
      </section>
    </div>
  );
}
