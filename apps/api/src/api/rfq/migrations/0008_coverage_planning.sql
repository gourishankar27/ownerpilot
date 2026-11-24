-- Additive planning policy; legacy counters, receipts and protocols remain intact.
alter table procurement.procurement_agent_runs add column planning_calls integer not null default 0 check(planning_calls between 0 and 4);
alter table procurement.procurement_agent_runs add column finalization_calls integer not null default 0 check(finalization_calls between 0 and 1);
alter table procurement.procurement_agent_runs add column planning_state jsonb not null default '{}';
alter table procurement.procurement_agent_runs add column coverage_state jsonb not null default '{}';
alter table procurement.procurement_agent_tool_calls add column execution_origin text not null default 'legacy_model' check(execution_origin in ('legacy_model','model_selected','backend_scheduled'));
alter table procurement.procurement_agent_tool_calls add column call_details jsonb not null default '{}';
