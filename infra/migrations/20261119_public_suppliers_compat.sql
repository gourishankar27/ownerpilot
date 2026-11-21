-- Explicit additive reconciliation for the existing Drizzle-owned public schema.
-- Legacy runtime DDL omitted suppliers. No existing table/constraint is dropped.
create table if not exists public.suppliers (
 id uuid primary key default gen_random_uuid(),
 workspace_id uuid not null,
 name varchar(160) not null,
 category varchar(120) not null,
 preferred_lead_days integer not null default 3,
 created_at timestamptz not null default now(),
 constraint suppliers_workspace_id_business_workspaces_id_fk
 foreign key(workspace_id) references public.business_workspaces(id) on delete cascade
);
