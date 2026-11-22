-- Additive: legacy runs retain their original metadata, results and counters.
alter table procurement.procurement_agent_runs add column finalization jsonb not null default '{}';
alter table procurement.procurement_agent_runs add column repair_attempts integer not null default 0 check(repair_attempts between 0 and 1);
alter table procurement.procurement_agent_runs add column diagnostics jsonb not null default '{}';
create table procurement.procurement_agent_finalizations (
 id uuid primary key default gen_random_uuid(),run_id uuid not null references procurement.procurement_agent_runs(id),
 phase text not null check(phase in ('initial','repair')),reference_request jsonb not null,
 resolution jsonb not null,created_at timestamptz not null default now(),unique(run_id,phase)
);
create table procurement.procurement_agent_model_calls (
 run_id uuid not null references procurement.procurement_agent_runs(id),ordinal integer not null,
 phase text not null check(phase in ('planning','finalization','repair')),state text not null,
 metrics jsonb not null default '{}',created_at timestamptz not null default now(),finished_at timestamptz,
 primary key(run_id,ordinal)
);
create trigger immutable_research_finalization before update or delete on procurement.procurement_agent_finalizations for each row execute function procurement.protect_procurement_evidence();
create trigger immutable_tool_receipt before update or delete on procurement.procurement_agent_tool_calls for each row execute function procurement.protect_procurement_evidence();
