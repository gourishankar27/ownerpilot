# @ownerpilot/web

Next.js App Router web application for OwnerPilot

## Scope
`apps/web` owns the user-facing product experience:
- marketing landing and onboarding flows
- authentication and workspace entry
- dashboard, imports, documents, investigation, action center, planner, reorder plan
- PWA shell optimized for Android and Windows browser install flows

## Key routes
- `/` marketing landing page
- `/dashboard` owner command center
- `/imports` historical data ingestion workflow
- `/documents` document upload and retrieval context
- `/ask` investigation workspace
- `/actions` action center lifecycle management
- `/planner` forecast and scenario workspace
- `/reorder` cash-aware replenishment workspace

## Local commands
- `pnpm dev`
- `pnpm build`
- `pnpm lint`
- `pnpm typecheck`
- `pnpm auth:migrate`
- `pnpm db:migrate`

## Environment expectations
- `NEXT_PUBLIC_API_BASE_URL` and `INTERNAL_API_BASE_URL` must point to the API runtime.
- `DATABASE_URL` and `AUTH_SECRET` are required for auth and server-side data access.

## Quality expectations
- keep UX copy grounded in real owner workflows
- keep type safety aligned with `@ownerpilot/contracts`
- update docs/screenshots when user-visible behavior changes
