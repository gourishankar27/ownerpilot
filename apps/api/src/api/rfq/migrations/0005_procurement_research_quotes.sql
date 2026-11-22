create table procurement.product_selection_resolutions (
 id uuid primary key default gen_random_uuid(),workspace_id uuid not null references public.business_workspaces(id),
 rfq_id uuid not null references procurement.rfqs(id),line_id uuid not null,revision integer not null,
 data jsonb not null,actor text not null,reason text not null,created_at timestamptz not null default now(),unique(rfq_id,line_id,revision)
);
create table procurement.supplier_offer_attestations (
 id uuid primary key default gen_random_uuid(),workspace_id uuid not null references public.business_workspaces(id),
 resolution_id uuid not null references procurement.product_selection_resolutions(id),data jsonb not null,
 price numeric(20,4),actor text not null,reason text not null,created_at timestamptz not null default now()
);
create table procurement.procurement_agent_runs (
 id uuid primary key default gen_random_uuid(),workspace_id uuid not null references public.business_workspaces(id),rfq_id uuid not null references procurement.rfqs(id),
 idempotency_key text not null,state text not null default 'queued' check(state in ('queued','planning','executing_tools','verifying','complete','needs_attention','failed','cancelled')),
 snapshot jsonb not null,messages jsonb not null default '[]',result jsonb,metadata jsonb not null default '{}',
 turns integer not null default 0,attempts integer not null default 0,actor text not null,error text,
 created_at timestamptz not null default now(),updated_at timestamptz not null default now(),unique(workspace_id,idempotency_key)
);
create unique index one_active_research_per_rfq on procurement.procurement_agent_runs(rfq_id) where state in ('queued','planning','executing_tools','verifying');
create table procurement.procurement_agent_tool_calls (
 id uuid primary key default gen_random_uuid(),run_id uuid not null references procurement.procurement_agent_runs(id),ordinal integer not null,
 tool text not null,schema_version text not null,arguments jsonb not null,argument_hash text not null,
 status text not null,policy text not null,result jsonb,error text,duration_ms numeric(14,3),
 started_at timestamptz not null default now(),finished_at timestamptz not null,unique(run_id,ordinal)
);
create table procurement.quote_drafts (
 id uuid primary key default gen_random_uuid(),workspace_id uuid not null references public.business_workspaces(id),rfq_id uuid not null references procurement.rfqs(id),
 revision integer not null default 1,state text not null default 'incomplete' check(state in ('draft','incomplete','under_review','changes_requested','approved_internal','rejected','superseded')),
 snapshot jsonb not null,policy jsonb not null,offer_choices jsonb not null default '{}',calculation jsonb not null,
 prepared_by text not null,approved_by text,approved_at timestamptz,created_at timestamptz not null default now(),updated_at timestamptz not null default now()
);
create table procurement.quote_versions (
 quote_id uuid not null references procurement.quote_drafts(id),revision integer not null,state text not null,
 data jsonb not null,grand_total numeric(24,4),actor text not null,reason text not null,created_at timestamptz not null default now(),primary key(quote_id,revision)
);
create table procurement.quote_audit_events (
 id bigint generated always as identity primary key,workspace_id uuid not null references public.business_workspaces(id),
 subject uuid not null,event text not null,actor text not null,details jsonb not null default '{}',created_at timestamptz not null default now()
);
create function procurement.protect_approved_quote() returns trigger language plpgsql as $$
begin
 if old.state='approved_internal' then raise exception 'Approved internal quote is immutable'; end if;
 return new;
end $$;
create trigger immutable_approved_quote before update or delete on procurement.quote_drafts for each row execute function procurement.protect_approved_quote();
create index quote_tenant on procurement.quote_drafts(workspace_id,rfq_id);
