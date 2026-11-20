-- Additive only. The procurement schema is exclusively owned by this migrator.
create table procurement.rfqs (
 id uuid primary key, workspace_id uuid not null references public.business_workspaces(id),
 title varchar(160) not null, status text not null default 'draft' check(status in ('draft','awaiting_review','approved')),
 revision integer not null default 0 check(revision >= 0), header jsonb not null default '{}',
 current_run_id uuid, created_by text not null, approved_by text, approved_at timestamptz,
 created_at timestamptz not null default now(), updated_at timestamptz not null default now(),
 unique(id,workspace_id), check ((status='approved') = (approved_at is not null and approved_by is not null))
);
create index rfqs_workspace_updated on procurement.rfqs(workspace_id,updated_at desc);
create table procurement.rfq_documents (
 id uuid primary key, rfq_id uuid not null, workspace_id uuid not null,
 filename varchar(160) not null, extension text not null check(extension in ('.pdf','.csv','.xlsx','.txt')),
 fingerprint char(64) not null, size_bytes bigint not null check(size_bytes > 0),
 status text not null default 'uploaded' check(status in ('uploaded','parsed','failed')),
 uploaded_by text not null, created_at timestamptz not null default now(),
 foreign key(rfq_id,workspace_id) references procurement.rfqs(id,workspace_id),
 unique(workspace_id,fingerprint), unique(id,workspace_id)
);
create index documents_rfq on procurement.rfq_documents(rfq_id);
create table procurement.rfq_processing_jobs (
 id uuid primary key, rfq_id uuid not null, workspace_id uuid not null,
 state text not null default 'queued' check(state in ('queued','validating','parsing','extracting','validating_results','awaiting_review','failed','cancelled')),
 mode text not null check(mode in ('deterministic','llm','hybrid')),
 base_revision integer not null, attempts integer not null default 0, completed_documents integer not null default 0,
 total_documents integer not null, stage_started_at timestamptz, started_at timestamptz, finished_at timestamptz,
 retryable boolean not null default false, error_category text, error_message text,
 requested_by text not null, created_at timestamptz not null default now(),
 foreign key(rfq_id,workspace_id) references procurement.rfqs(id,workspace_id), unique(id,workspace_id)
);
create unique index one_active_rfq_job on procurement.rfq_processing_jobs(rfq_id)
 where state in ('queued','validating','parsing','extracting','validating_results');
create index jobs_dispatch on procurement.rfq_processing_jobs(state,stage_started_at);
create table procurement.rfq_document_pages (
 document_id uuid not null references procurement.rfq_documents(id),
 parser_version text not null, content jsonb not null, created_at timestamptz not null default now(),
 primary key(document_id,parser_version)
);
create table procurement.rfq_extraction_runs (
 id uuid primary key, job_id uuid not null unique references procurement.rfq_processing_jobs(id),
 rfq_id uuid not null, workspace_id uuid not null, schema_version text not null,
 result jsonb not null, metadata jsonb not null, created_at timestamptz not null default now(),
 foreign key(rfq_id,workspace_id) references procurement.rfqs(id,workspace_id), unique(id,rfq_id)
);
alter table procurement.rfqs add constraint current_run_fk foreign key(current_run_id,id)
 references procurement.rfq_extraction_runs(id,rfq_id);
create table procurement.rfq_line_items (
 run_id uuid not null references procurement.rfq_extraction_runs(id), id uuid not null,
 rfq_id uuid not null, workspace_id uuid not null, data jsonb not null,
 quantity numeric(20,6), requested_unit_price numeric(20,6),
 primary key(run_id,id), foreign key(rfq_id,workspace_id) references procurement.rfqs(id,workspace_id),
 check(quantity is null or quantity > 0), check(requested_unit_price is null or requested_unit_price >= 0)
);
create index items_rfq on procurement.rfq_line_items(rfq_id,run_id);
create table procurement.rfq_audit_events (
 id bigint generated always as identity primary key, rfq_id uuid not null, workspace_id uuid not null,
 actor text not null, event text not null, run_id uuid references procurement.rfq_extraction_runs(id),
 details jsonb not null default '{}', created_at timestamptz not null default now(),
 foreign key(rfq_id,workspace_id) references procurement.rfqs(id,workspace_id)
);
create index audit_rfq on procurement.rfq_audit_events(rfq_id,id desc);
