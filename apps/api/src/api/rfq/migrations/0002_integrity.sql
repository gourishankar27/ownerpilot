-- Strengthen version/ownership consistency without modifying migration 0001.
alter table procurement.rfq_line_items add constraint item_run_rfq_fk
 foreign key(run_id,rfq_id) references procurement.rfq_extraction_runs(id,rfq_id);
alter table procurement.rfq_audit_events add constraint audit_run_rfq_fk
 foreign key(run_id,rfq_id) references procurement.rfq_extraction_runs(id,rfq_id);
alter table procurement.rfq_processing_jobs add constraint job_counters_valid
 check(attempts >= 0 and total_documents > 0 and completed_documents >= 0 and completed_documents <= total_documents);
