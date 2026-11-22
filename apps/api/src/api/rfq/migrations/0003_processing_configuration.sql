-- Historical jobs retain Phase 1 behavior; new jobs explicitly persist their policy.
alter table procurement.rfq_processing_jobs add column configuration jsonb not null
 default '{"policy":"phase1","ocr_strategy":"legacy-v1"}'::jsonb;
alter table procurement.rfq_processing_jobs add constraint valid_processing_configuration
 check (jsonb_typeof(configuration)='object');
