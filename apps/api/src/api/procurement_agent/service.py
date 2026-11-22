"""Versioned reviewed selections, local offers and immutable quote preparation."""

import hashlib
import json

from fastapi import HTTPException
from fastapi.encoders import jsonable_encoder
from psycopg.types.json import Jsonb

from api.catalog.routes import approved_query
from api.rfq.repository import load_rfq, items

from .finance import Commercial, QuotePolicy, calculate, freshness, number


def canonical(value):
    return json.dumps(jsonable_encoder(value), sort_keys=True, separators=(",", ":"))


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def audit(conn, identity, subject, event, details=None):
    conn.execute(
        "insert into procurement.quote_audit_events(workspace_id,subject,event,actor,details) values(%s,%s,%s,%s,%s)",
        (identity.workspace_id, subject, event, identity.user_id, Jsonb(details or {})),
    )


def owned(conn, table, identifier, identity, lock=False):
    if table not in {
        "product_selection_resolutions",
        "supplier_offer_attestations",
        "quote_drafts",
        "procurement_agent_runs",
    }:
        raise ValueError("Closed table allowlist")
    row = conn.execute(
        f"select * from procurement.{table} where id=%s and workspace_id=%s"
        + (" for update" if lock else ""),
        (identifier, identity.workspace_id),
    ).fetchone()
    if not row:
        raise HTTPException(404, "Authorized resource not found")
    return row


def selection(conn, rfq_id, line_id, identity):
    rfq, query = approved_query(conn, rfq_id, line_id, identity)
    runs = conn.execute(
        "select * from procurement.catalog_match_runs where workspace_id=%s and rfq_id=%s and item_id=%s and revision=%s order by created_at desc,id desc limit 2",
        (identity.workspace_id, rfq_id, line_id, rfq["revision"]),
    ).fetchall()
    resolution = conn.execute(
        "select * from procurement.product_selection_resolutions where workspace_id=%s and rfq_id=%s and line_id=%s order by revision desc limit 1",
        (identity.workspace_id, rfq_id, line_id),
    ).fetchone()
    current = runs[0] if runs else None
    reviews = (
        conn.execute(
            "select * from procurement.catalog_match_reviews where run_id=%s order by id",
            (current["id"],),
        ).fetchall()
        if current
        else []
    )
    selected = {r["product_id"] for r in reviews if r["decision"] == "select"}
    rejected = {r["product_id"] for r in reviews if r["decision"] == "reject"}
    no_match = any(r["decision"] == "no_match" for r in reviews)
    state = (
        "conflicting_reviews"
        if len(selected) > 1 or selected & rejected or (selected and no_match)
        else "consensus"
        if selected
        else "no_match"
        if no_match
        else "rejected"
        if rejected
        else "superseded_search"
        if len(runs) > 1
        else "no_selection"
    )
    review_digest = digest(reviews)
    if resolution:
        data = resolution["data"]
        if (
            not current
            or str(current["id"]) != data["run_id"]
            or review_digest != data["review_digest"]
        ):
            state = "superseded_search_or_review"
        elif data["decision"] == "no_match":
            state = "no_match"
        else:
            version = conn.execute(
                "select v.state,c.active_version from procurement.catalog_versions v join procurement.product_catalogs c on c.id=v.catalog_id where v.id=%s and v.workspace_id=%s for share of v,c",
                (data["version_id"], identity.workspace_id),
            ).fetchone()
            state = (
                "resolved"
                if version
                and version["state"] == "published"
                and str(version["active_version"]) == data["version_id"]
                else "stale_catalog"
            )
    return jsonable_encoder(
        {
            "line_id": line_id,
            "query": query,
            "state": state,
            "revision": resolution["revision"] if resolution else 0,
            "resolution": resolution,
            "current_run_id": current["id"] if current else None,
            "reviews": reviews,
            "review_digest": review_digest,
            "candidates": current["result"]["candidates"] if current else [],
        }
    )


def resolve(conn, rfq_id, line_id, payload, identity):
    identity.require_approve()
    load_rfq(conn, rfq_id, identity.workspace_id, True)
    view = selection(conn, rfq_id, line_id, identity)
    if view["revision"] != payload.expected_revision or view["current_run_id"] != str(
        payload.run_id
    ):
        raise HTTPException(409, "Selection/search changed; reload before resolving")
    data = {
        "decision": payload.decision,
        "run_id": str(payload.run_id),
        "review_digest": view["review_digest"],
        "query": view["query"],
    }
    if payload.decision == "select":
        candidate = next(
            (c for c in view["candidates"] if c["id"] == payload.product_id), None
        )
        if not candidate or not any(
            r["decision"] == "select" and r["product_id"] == payload.product_id
            for r in view["reviews"]
        ):
            raise HTTPException(422, "Explicit positive product review required")
        compatibility = candidate["compatibility"]["status"]
        if compatibility not in {"exact", "compatible_alternative"} or (
            compatibility == "compatible_alternative"
            and not payload.alternative_attested
        ):
            raise HTTPException(
                422, "Compatibility evidence and alternative attestation required"
            )
        sources = {s["version_id"] for s in candidate["sources"]}
        if str(payload.version_id) not in sources:
            raise HTTPException(
                422, "Product/version does not belong to reviewed evidence"
            )
        product = conn.execute(
            "select p.*,v.state,c.active_version,v.fingerprint from procurement.catalog_products p join procurement.catalog_versions v on p.version_id=v.id join procurement.product_catalogs c on c.id=v.catalog_id where p.version_id=%s and p.id=%s and p.workspace_id=%s",
            (payload.version_id, payload.product_id, identity.workspace_id),
        ).fetchone()
        if (
            not product
            or product["state"] != "published"
            or product["active_version"] != payload.version_id
        ):
            raise HTTPException(409, "Catalog is no longer current")
        data.update(
            product_id=payload.product_id,
            version_id=str(payload.version_id),
            product=product["data"],
            content_hash=product["content_hash"],
            catalog_fingerprint=product["fingerprint"],
            compatibility=candidate["compatibility"],
            alternative_attested=payload.alternative_attested,
            sources=candidate["sources"],
        )
    elif payload.product_id or payload.version_id:
        raise HTTPException(422, "No-match cannot reference a product")
    row = conn.execute(
        "insert into procurement.product_selection_resolutions(workspace_id,rfq_id,line_id,revision,data,actor,reason) values(%s,%s,%s,%s,%s,%s,%s) returning *",
        (
            identity.workspace_id,
            rfq_id,
            line_id,
            view["revision"] + 1,
            Jsonb(data),
            identity.user_id,
            payload.reason,
        ),
    ).fetchone()
    audit(
        conn,
        identity,
        row["id"],
        "selection_resolved",
        {"decision": payload.decision, "revision": row["revision"]},
    )
    return row


def commercial_review_state(offer, offers):
    superseded = {entry["data"].get("supersedes_id") for entry in offers}
    if str(offer["id"]) in superseded:
        return "superseded"
    value = offer["data"]["commercial"]
    peers = [
        entry
        for entry in offers
        if str(entry["id"]) not in superseded
        and entry["data"]["commercial"]["supplier"] == value["supplier"]
        and entry["data"]["commercial"].get("supplier_sku") == value.get("supplier_sku")
    ]
    return (
        "conflicting_information"
        if len({digest(entry["data"]["commercial"]) for entry in peers}) > 1
        else "active_attestation"
    )


def local_offers(conn, resolution, identity):
    data = resolution["data"]
    product = conn.execute(
        "select offers from procurement.catalog_products where workspace_id=%s and version_id=%s and id=%s",
        (identity.workspace_id, data["version_id"], data["product_id"]),
    ).fetchone()
    imported = (
        [
            {
                "data_class": "imported_catalog_metadata",
                "freshness": "unknown_freshness",
                "commercial_source_date": None,
                "catalog_version": data["version_id"],
                "source_fingerprint": data["content_hash"],
                **offer,
            }
            for offer in product["offers"]
        ]
        if product
        else []
    )
    attestations = conn.execute(
        "select * from procurement.supplier_offer_attestations where workspace_id=%s and resolution_id=%s order by created_at,id",
        (identity.workspace_id, resolution["id"]),
    ).fetchall()
    return jsonable_encoder(
        {
            "imported": imported,
            "attestations": [
                {
                    **r,
                    **(
                        {
                            "commercial_review_state": commercial_review_state(
                                r, attestations
                            )
                        }
                        if commercial_review_state(r, attestations)
                        != "active_attestation"
                        else {}
                    ),
                    "data_class": "user_attested",
                    "freshness": freshness(
                        Commercial.model_validate(r["data"]["commercial"])
                    ),
                }
                for r in attestations
            ],
        }
    )


def attest(conn, payload, identity):
    identity.require_approve()
    resolution = owned(
        conn, "product_selection_resolutions", payload.resolution_id, identity
    )
    load_rfq(conn, resolution["rfq_id"], identity.workspace_id, True)
    current = selection(conn, resolution["rfq_id"], resolution["line_id"], identity)
    if current["state"] != "resolved" or current["resolution"]["id"] != str(
        payload.resolution_id
    ):
        raise HTTPException(409, "Attestation requires current resolved selection")
    commercial = payload.commercial
    if commercial.price is not None:
        number(commercial.price)
    if commercial.minimum_units is not None:
        number(commercial.minimum_units, maximum="1000000")
    if commercial.stock_units is not None:
        number(commercial.stock_units, maximum="1000000")
    thresholds = set()
    for tier in commercial.breaks:
        threshold = number(tier.minimum_units, positive=True, maximum="1000000")
        number(tier.price)
        if threshold in thresholds:
            raise HTTPException(422, "Duplicate quantity break")
        thresholds.add(threshold)
    if payload.source_offer_id:
        imported = local_offers(conn, resolution, identity)["imported"]
        if not any(o.get("source_id") == payload.source_offer_id for o in imported):
            raise HTTPException(
                422, "Source offer is not part of selected product/version"
            )
    data = {
        "commercial": commercial.model_dump(mode="json"),
        "source_offer_id": payload.source_offer_id,
        "product_id": resolution["data"]["product_id"],
        "version_id": resolution["data"]["version_id"],
        "source_fingerprint": resolution["data"]["content_hash"],
        "supersedes_id": str(payload.supersedes_id) if payload.supersedes_id else None,
    }
    if payload.supersedes_id:
        previous = owned(
            conn, "supplier_offer_attestations", payload.supersedes_id, identity
        )
        if previous["resolution_id"] != payload.resolution_id:
            raise HTTPException(
                422, "Superseded offer must belong to the same resolution"
            )
    row = conn.execute(
        "insert into procurement.supplier_offer_attestations(workspace_id,resolution_id,data,price,actor,reason) values(%s,%s,%s,%s,%s,%s) returning *",
        (
            identity.workspace_id,
            payload.resolution_id,
            Jsonb(data),
            commercial.price,
            identity.user_id,
            payload.reason,
        ),
    ).fetchone()
    audit(
        conn,
        identity,
        row["id"],
        "offer_attested",
        {"resolution_id": str(payload.resolution_id), "data_class": "user_attested"},
    )
    return row


def snapshot(conn, rfq_id, identity):
    rfq = load_rfq(conn, rfq_id, identity.workspace_id)
    if rfq["status"] != "approved":
        raise HTTPException(409, "Current approved RFQ required")
    lines = []
    for item in items(conn, rfq):
        if item.review_status == "excluded":
            continue
        view = selection(conn, rfq_id, item.id, identity)
        fields = {k: v.model_dump(mode="json") for k, v in item.fields.items()}
        quantity = item.fields.get("quantity")
        unit = item.fields.get("unit")
        lines.append(
            {
                "line_id": item.id,
                "quantity": quantity.value
                if quantity and quantity.status == "validated"
                else None,
                "unit": unit.value if unit and unit.status == "validated" else None,
                "fields": fields,
                "selection": view,
                "offers": local_offers(conn, view["resolution"], identity)
                if view["state"] == "resolved"
                else {"imported": [], "attestations": []},
            }
        )
    if len(lines) > 100:
        raise HTTPException(422, "Phase 3 limit: 100 lines per research/quote")
    return jsonable_encoder(
        {
            "rfq_id": rfq_id,
            "revision": rfq["revision"],
            "source_run": rfq["current_run_id"],
            "header": rfq["header"],
            "lines": lines,
        }
    )


def quote_calculation(source, choices, policy):
    if set(choices) - {entry["line_id"] for entry in source["lines"]}:
        raise HTTPException(422, "Unknown quote line")
    lines = []
    problems = []
    for line in source["lines"]:
        if line["selection"]["state"] != "resolved":
            problems.append(line["line_id"] + ":reviewed_selection_unresolved")
        # Only each/EA is supported. No inferred unit, currency or pack conversions.
        if (line.get("unit") or "").upper() not in {
            "EA",
            "EACH",
            "UNIT",
            "UNITS",
            "PCS",
            "PC",
        }:
            problems.append(line["line_id"] + ":rfq_unit_conversion_unresolved")
        offer_id = str(choices.get(line["line_id"], ""))
        offer = next(
            (o for o in line["offers"]["attestations"] if o["id"] == offer_id), None
        )
        superseded = {
            o["data"].get("supersedes_id") for o in line["offers"]["attestations"]
        }
        if offer_id in superseded:
            problems.append(line["line_id"] + ":offer_superseded")
        if offer:
            supplier = offer["data"]["commercial"]["supplier"]
            sku = offer["data"]["commercial"].get("supplier_sku")
            alternatives = [
                o
                for o in line["offers"]["attestations"]
                if o["id"] not in superseded
                and o["data"]["commercial"]["supplier"] == supplier
                and o["data"]["commercial"].get("supplier_sku") == sku
            ]
            if len({digest(o["data"]["commercial"]) for o in alternatives}) > 1:
                problems.append(
                    line["line_id"]
                    + ":conflicting_supplier_attestations_require_explicit_supersession"
                )
        if offer_id and not offer:
            raise HTTPException(
                422, "Offer is not authorized for the selected line and resolution"
            )
        lines.append(
            {
                "line_id": line["line_id"],
                "quantity": line["quantity"],
                "offer_id": offer_id or None,
                "offer": offer["data"]["commercial"] if offer else None,
            }
        )
    result = calculate(lines, policy)
    result["issues"].extend(problems)
    result["complete"] = not result["issues"]
    if problems:
        result["grand_total"] = None
    return result


def stable_source(source):
    return {
        "rfq_id": source["rfq_id"],
        "revision": source["revision"],
        "source_run": source["source_run"],
        "lines": [
            {
                "line_id": entry["line_id"],
                "quantity": entry["quantity"],
                "unit": entry["unit"],
                "resolution_id": (entry["selection"].get("resolution") or {}).get("id"),
                "state": entry["selection"]["state"],
                "review_digest": entry["selection"]["review_digest"],
                "offer_fingerprints": sorted(
                    (o["id"], digest(o["data"]))
                    for o in entry["offers"]["attestations"]
                ),
            }
            for entry in source["lines"]
        ],
    }


def record_quote(conn, row, identity, reason):
    data = jsonable_encoder(row)
    conn.execute(
        "insert into procurement.quote_versions(quote_id,revision,state,data,grand_total,actor,reason) values(%s,%s,%s,%s,%s,%s,%s)",
        (
            row["id"],
            row["revision"],
            row["state"],
            Jsonb(data),
            row["calculation"].get("grand_total"),
            identity.user_id,
            reason,
        ),
    )
    audit(
        conn,
        identity,
        row["id"],
        "quote_" + row["state"],
        {"revision": row["revision"], "reason": reason},
    )


def create_quote(conn, rfq_id, payload, identity):
    identity.require_write()
    load_rfq(conn, rfq_id, identity.workspace_id, True)
    source = snapshot(conn, rfq_id, identity)
    choices = {k: str(v) for k, v in payload.offer_choices.items()}
    calculation = quote_calculation(source, choices, payload.policy)
    row = conn.execute(
        "insert into procurement.quote_drafts(workspace_id,rfq_id,state,snapshot,policy,offer_choices,calculation,prepared_by) values(%s,%s,%s,%s,%s,%s,%s,%s) returning *",
        (
            identity.workspace_id,
            rfq_id,
            "draft" if calculation["complete"] else "incomplete",
            Jsonb(source),
            Jsonb(payload.policy.model_dump(mode="json")),
            Jsonb(choices),
            Jsonb(calculation),
            identity.user_id,
        ),
    ).fetchone()
    record_quote(conn, row, identity, payload.reason)
    return row


def quote_change(conn, quote_id, payload, identity, action):
    identity.require_approve() if action in {
        "approve",
        "reject",
        "request-changes",
    } else identity.require_write()
    row = owned(conn, "quote_drafts", quote_id, identity, True)
    if row["revision"] != payload.revision:
        raise HTTPException(409, "Quote revision changed; reload")
    if row["state"] in {"approved_internal", "rejected", "superseded"}:
        raise HTTPException(409, "Final quote is immutable; create a new draft version")
    load_rfq(conn, row["rfq_id"], identity.workspace_id, True)
    if action == "edit":
        if row["state"] == "under_review":
            raise HTTPException(409, "Request changes before editing a submitted quote")
        source = snapshot(conn, row["rfq_id"], identity)
        policy = payload.policy
        choices = {k: str(v) for k, v in payload.offer_choices.items()}
        calculation = quote_calculation(source, choices, policy)
        state = "draft" if calculation["complete"] else "incomplete"
    else:
        source = row["snapshot"]
        policy = QuotePolicy.model_validate(row["policy"])
        choices = row["offer_choices"]
        current = snapshot(conn, row["rfq_id"], identity)
        if action in {"submit", "approve"} and stable_source(source) != stable_source(
            current
        ):
            raise HTTPException(
                409, "Reviewed sources changed; edit and recalculate quote"
            )
        calculation = quote_calculation(source, choices, policy)
        state = {
            "submit": "under_review",
            "approve": "approved_internal",
            "reject": "rejected",
            "request-changes": "changes_requested",
            "supersede": "superseded",
        }[action]
        if action in {"submit", "approve"}:
            if not calculation["complete"]:
                raise HTTPException(
                    409,
                    {
                        "message": "Unresolved commercial inputs block review/approval",
                        "issues": calculation["issues"],
                    },
                )
            if not payload.inputs_reviewed:
                raise HTTPException(
                    422, "Explicit commercial inputs review attestation required"
                )
        if (
            action in {"approve", "reject", "request-changes"}
            and row["state"] != "under_review"
        ):
            raise HTTPException(409, "Quote must be under review")
        if action == "submit" and row["state"] not in {
            "draft",
            "changes_requested",
            "incomplete",
        }:
            raise HTTPException(409, "Quote already submitted")
    row = conn.execute(
        "update procurement.quote_drafts set revision=revision+1,state=%s,snapshot=%s,policy=%s,offer_choices=%s,calculation=%s,approved_by=%s,approved_at=case when %s='approved_internal' then now() else null end,updated_at=now() where id=%s returning *",
        (
            state,
            Jsonb(source),
            Jsonb(policy.model_dump(mode="json")),
            Jsonb(choices),
            Jsonb(calculation),
            identity.user_id if state == "approved_internal" else None,
            state,
            quote_id,
        ),
    ).fetchone()
    record_quote(conn, row, identity, payload.reason)
    return row
