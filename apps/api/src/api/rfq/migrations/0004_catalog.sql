create table procurement.product_catalogs (
 id uuid primary key default gen_random_uuid(), workspace_id uuid not null references public.business_workspaces(id),
 name text not null, license text not null, active_version uuid, created_at timestamptz not null default now()
);
create table procurement.catalog_versions (
 id uuid primary key default gen_random_uuid(), catalog_id uuid not null references procurement.product_catalogs(id),
 workspace_id uuid not null references public.business_workspaces(id), fingerprint text not null,
 specification jsonb not null, rows jsonb not null, state text not null default 'preview' check(state in ('preview','queued','building','published','superseded','failed')),
 generation integer not null default 1, attempts integer not null default 0, model text, digest text,
 metadata jsonb not null default '{}', error text, requested_by text not null, created_at timestamptz not null default now(), started_at timestamptz, finished_at timestamptz,
 unique(catalog_id,fingerprint)
);
alter table procurement.product_catalogs add foreign key(active_version) references procurement.catalog_versions(id);
create table procurement.catalog_products (
 version_id uuid not null references procurement.catalog_versions(id), id text not null, workspace_id uuid not null references public.business_workspaces(id),
 identity_hash text not null, data jsonb not null, offers jsonb not null, content_hash text not null,
 embedding vector(768) not null, primary key(version_id,id), unique(version_id,identity_hash)
);
create index catalog_products_tenant on procurement.catalog_products(workspace_id,version_id);
create table procurement.catalog_match_runs (
 id uuid primary key default gen_random_uuid(), workspace_id uuid not null references public.business_workspaces(id),
 rfq_id uuid not null references procurement.rfqs(id), item_id uuid not null, revision integer not null,
 query jsonb not null, versions jsonb not null, result jsonb not null, created_by text not null, created_at timestamptz not null default now()
);
create table procurement.catalog_match_reviews (
 id uuid primary key default gen_random_uuid(), run_id uuid not null references procurement.catalog_match_runs(id),
 actor text not null, decision text not null check(decision in ('select','reject','no_match')), product_id text,
 note text not null, created_at timestamptz not null default now(), unique(run_id,actor)
);
create table procurement.catalog_audit_events (
 id bigint generated always as identity primary key, workspace_id uuid not null references public.business_workspaces(id),
 actor text not null, event text not null, subject uuid not null, details jsonb not null, created_at timestamptz not null default now()
);
