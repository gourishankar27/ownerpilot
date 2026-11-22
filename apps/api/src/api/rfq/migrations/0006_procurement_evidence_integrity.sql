-- Preserve exact numeric attestation precision; JSON strings remain authoritative inputs.
alter table procurement.supplier_offer_attestations alter column price type numeric(28,12);
alter table procurement.quote_versions alter column grand_total type numeric(30,4);

-- Evidence/revisions are append-only even for an accidental backend update.
create function procurement.protect_procurement_evidence() returns trigger language plpgsql as $$
begin
 raise exception 'Procurement evidence and quote history are append-only';
end $$;
create trigger immutable_selection_resolution before update or delete on procurement.product_selection_resolutions for each row execute function procurement.protect_procurement_evidence();
create trigger immutable_offer_attestation before update or delete on procurement.supplier_offer_attestations for each row execute function procurement.protect_procurement_evidence();
create trigger immutable_quote_version before update or delete on procurement.quote_versions for each row execute function procurement.protect_procurement_evidence();
create trigger immutable_quote_audit before update or delete on procurement.quote_audit_events for each row execute function procurement.protect_procurement_evidence();
