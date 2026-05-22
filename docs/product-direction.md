# Product Direction

## Rebrand decision

Chosen name: **OwnerPilot**.

Why it fits:
- broad enough for inventory, cash, suppliers, documents, forecasts, and future customer workflows
- simple to explain: a practical copilot for owner decisions
- less loaded than the old acronym and easier to present in a portfolio or demo
- still aligned with the current product promise: evidence-backed operating decisions for small businesses

## Naming shortlist considered

| Name | Fit | Reason to pass or keep |
| --- | --- | --- |
| OwnerPilot | Best fit | Broad, owner-first, easy to extend beyond dashboards. |
| LocalOps AI | Good | Strong for local businesses, but sounds more like an agency or internal tool. |
| LedgerPilot | Good | Clear financial signal, but too ledger-heavy for inventory and documents. |
| MarginMate | Narrow | Friendly, but focuses too much on margin only. |
| TradeWise | Good | Commerce-friendly, but less distinctive and less owner-specific. |

## Feature direction

OwnerPilot should become an owner operating cockpit, not just an analytics dashboard. The feature set should move from “what happened?” to “what should I do next?”

### Feature roadmap

1. **Cash-aware Reorder Plan** — inventory replenishment recommendations using stock, sales velocity, supplier cost, expiry risk, and obligation pressure.
2. **Cash Calendar** — combine expected sales, purchases, recurring bills, and supplier payments into a day-by-day runway view.
3. **Supplier Desk** — supplier profiles, lead times, recent purchase prices, negotiation notes, and follow-up drafts.
4. **Invoice and Bill Extraction** — upload PDFs/images and convert them into structured expenses, purchases, and obligations.
5. **Pricing and Margin Advisor** — flag SKUs where price, cost, or discounting is hurting profit conversion.
6. **Customer Credit Follow-up** — track receivables, credit customers, reminders, and safe follow-up messages.
7. **Tax/GST Pack** — India-first export pack for sales, purchases, expenses, and supporting documents.
8. **Industry Templates** — pharmacy first, then grocery/kirana, salon, repair shop, clinic, restaurant, and services.
9. **Mobile Daily Close** — end-of-day mobile flow for cash, UPI, card, expenses, and notes.
10. **Alerts and WhatsApp-ready Briefs** — scheduled briefs that produce owner-readable reminders and suggested actions.

## First implemented feature

The first feature added in this iteration is **Cash-aware Reorder Plan**.

Implemented surfaces:
- `GET /api/reorder-plan?horizonDays=14`
- shared contract schemas for reorder plan results and items
- web API client and fallback data
- `/reorder` route in the app shell
- interactive horizon controls for 7, 14, 30, and 45 day plans
- documentation updates across README, architecture, API, web, roadmap, and showcase runbook

The initial model is intentionally deterministic so demos stay reproducible. It can later be upgraded with supplier lead times, service-level targets, purchase-order approvals, and true cash balance integration.
