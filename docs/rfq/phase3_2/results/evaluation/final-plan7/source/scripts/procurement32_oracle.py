"""Independent authored-fact/source association oracle: standard library only.

No production resolver, tool execution, calculator or model is imported here.
"""

import hashlib
import json
import re


def fingerprint(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()


def equal(left, right):
    return type(left) is type(right) and left == right


def tokens(pointer):
    if not isinstance(pointer, str) or not pointer.startswith("/data/"):
        raise ValueError("pointer_root")
    result = []
    for token in pointer[1:].split("/"):
        if re.search(r"~(?![01])", token):
            raise ValueError("pointer_escape")
        result.append(token.replace("~1", "/").replace("~0", "~"))
    return result


def value_at(document, path):
    value = document
    for token in path:
        if isinstance(value, list):
            if not re.fullmatch(r"0|[1-9][0-9]*", token):
                raise ValueError("pointer_index")
            value = value[int(token)]
        else:
            value = value[token]
    if type(value) in {dict, list}:
        raise ValueError("non_scalar")
    return value


def audit(case, item, run, result, receipts):
    bindings = {
        binding["line_id"]: (line, binding)
        for line in case["lines"]
        for binding in [item["lines"][line["key"]]]
    }
    expected = set()
    wanted_unknowns = set()
    for identifier, (line, binding) in bindings.items():
        expected.add((identifier, None, "selection_state"))
        if line["selection"] != "resolved":
            wanted_unknowns.add(
                (identifier, None, "product_selection", line["selection"])
            )
        if not line["offers"]:
            wanted_unknowns.add(
                (identifier, None, "attested_supplier_offer", "missing")
            )
        for offer in line["offers"]:
            offer_id = binding["offers"][offer["key"]]
            expected.update(
                (identifier, offer_id, field)
                for field in ["price", "currency", "availability", "freshness"]
            )
            if offer["expected_review_state"] != "active_attestation":
                expected.add((identifier, offer_id, "review_state"))
            for field in [
                "price",
                "currency",
                "availability",
                "lead_time_days",
                "stock_units",
                "observed_on",
                "valid_until",
            ]:
                if offer["commercial"].get(field) in {None, "unknown"}:
                    wanted_unknowns.add((identifier, offer_id, field, "unknown"))
    required_reads = {
        (line, kind)
        for line in bindings
        for kind in ["get_reviewed_product_selection", "get_supplier_offers"]
    }
    seen_reads = set()
    approved = False
    invalid, source_errors, valid_receipts = [], [], set()
    unauthorized_successful = 0
    model_calls = backend_calls = 0
    model_source_pairs = set()
    backend_source_pairs = set()
    duplicate_reads = 0
    batch_lines = []
    optional_calls = 0
    useful_model_calls = 0

    def verify_selection(data, identifier):
        line, binding = bindings[identifier]
        if data.get("line_id") != identifier or data.get("state") != line["selection"]:
            raise ValueError("selection_association")
        resolution = data.get("resolution") or {}
        if resolution.get("id") != binding["resolution_id"]:
            raise ValueError("selection_resolution")
        product = resolution.get("data", {})
        if (
            product.get("product_id") != binding["product_id"]
            or product.get("version_id") != binding["version_id"]
        ):
            raise ValueError("selection_product")

    def verify_offers(data, identifier):
        line, binding = bindings[identifier]
        if (
            data.get("line_id") != identifier
            or data.get("selection_state") != line["selection"]
        ):
            raise ValueError("offer_line")
        actual = data.get("attestations")
        if not isinstance(actual, list) or len(actual) != len(line["offers"]):
            raise ValueError("missing_offer")
        lookup = {offer["id"]: offer for offer in actual}
        if set(lookup) != set(binding["offers"].values()):
            raise ValueError("offer_identity")
        for authored in line["offers"]:
            source = lookup[binding["offers"][authored["key"]]]
            for name, wanted in authored["commercial"].items():
                if not equal(source.get(name), wanted):
                    raise ValueError("source_commercial_value")
            for name, wanted in {
                "resolution_id": binding["resolution_id"],
                "product_id": binding["product_id"],
                "version_id": binding["version_id"],
                "source_fingerprint": binding["fingerprint"],
                "data_class": "user_attested",
                "freshness": authored["expected_freshness"],
            }.items():
                if source.get(name) != wanted:
                    raise ValueError("offer_source_association")
            if (
                source.get("commercial_review_state", "active_attestation")
                != authored["expected_review_state"]
            ):
                raise ValueError("commercial_review")

    for receipt in receipts:
        origin = receipt.get("execution_origin", "legacy_model")
        if origin == "backend_scheduled":
            backend_calls += 1
        else:
            model_calls += 1
        name, args = receipt["tool"], receipt["arguments"]
        scoped = (
            name in case["expected"]["allowed_tools"]
            and str(receipt["run_id"]) == str(run["id"])
            and receipt["schema_version"] == run["metadata"]["tool_schema"]
        )
        if name == "get_line_research_batch":
            ids = args.get("line_ids", [])
            include = args.get(
                "include", ["reviewed_product_selection", "supplier_offers"]
            )
            scoped = (
                scoped
                and set(args) <= {"line_ids", "include"}
                and isinstance(ids, list)
                and 1 <= len(ids) <= run["metadata"].get("batch_size", 4)
                and len(set(ids)) == len(ids)
                and not (set(ids) - set(bindings))
                and isinstance(include, list)
                and 1 <= len(include) <= 2
                and len(set(include)) == len(include)
                and not (
                    set(include) - {"reviewed_product_selection", "supplier_offers"}
                )
            )
        elif name in {
            "get_approved_rfq",
            "get_quote_requirements",
            "calculate_quote_preview",
        }:
            scoped = scoped and not args
        elif "line_id" in args:
            scoped = (
                scoped
                and args["line_id"] in bindings
                and set(args)
                <= ({"line_id", "method"} if name == "search_catalog" else {"line_id"})
            )
        elif name == "check_offer_freshness":
            scoped = (
                scoped
                and args.get("offer_id")
                in {
                    offer
                    for _, binding in bindings.values()
                    for offer in binding["offers"].values()
                }
                and set(args) == {"offer_id"}
            )
        else:
            scoped = False
        if receipt["status"] != "succeeded":
            continue
        if not scoped:
            unauthorized_successful += 1
            continue
        additions = set()
        was_approved = approved
        try:
            body = receipt["result"]
            if name == "get_approved_rfq":
                if body.get("rfq_id") != run["snapshot"]["rfq_id"] or not equal(
                    body.get("revision"), item["revision"]
                ):
                    raise ValueError("rfq_revision")
                if {line["line_id"] for line in body["lines"]} != set(bindings) or len(
                    body["lines"]
                ) != len(bindings):
                    raise ValueError("rfq_scope")
                approved = True
            elif name == "get_line_research_batch":
                if (
                    set(body) != {"lines", "complete", "requested_line_ids"}
                    or body["complete"] is not True
                    or body["requested_line_ids"] != ids
                    or len(body["lines"]) != len(ids)
                ):
                    raise ValueError("incomplete_batch")
                for identifier, entry in zip(ids, body["lines"]):
                    keys = (
                        {"line_id", "source_status"}
                        | (
                            {"selection"}
                            if "reviewed_product_selection" in include
                            else set()
                        )
                        | ({"offers"} if "supplier_offers" in include else set())
                    )
                    if (
                        set(entry) != keys
                        or entry["line_id"] != identifier
                        or entry["source_status"] != "inspected"
                    ):
                        raise ValueError("batch_line_association")
                    if "reviewed_product_selection" in include:
                        verify_selection(entry["selection"], identifier)
                        additions.add((identifier, "get_reviewed_product_selection"))
                    if "supplier_offers" in include:
                        verify_offers(entry["offers"], identifier)
                        additions.add((identifier, "get_supplier_offers"))
                batch_lines.append(len(ids))
            elif name == "get_reviewed_product_selection":
                verify_selection(body, args["line_id"])
                additions.add((args["line_id"], name))
            elif name == "get_supplier_offers":
                verify_offers(body, args["line_id"])
                additions.add((args["line_id"], name))
            else:
                optional_calls += 1
            valid_receipts.add(str(receipt["id"]))
            duplicate_reads += len(additions & seen_reads) + (
                1 if name == "get_approved_rfq" and was_approved else 0
            )
            new = additions - seen_reads
            if origin == "backend_scheduled":
                backend_source_pairs.update(new)
            else:
                model_source_pairs.update(new)
                useful_model_calls += bool(new or approved != was_approved)
            seen_reads.update(additions)
        except (ValueError, KeyError, TypeError, IndexError) as exc:
            source_errors.append(
                {
                    "receipt_id": str(receipt["id"]),
                    "code": str(exc) if type(exc) is ValueError else "malformed_source",
                }
            )

    seen = set()
    receipt_map = {str(receipt["id"]): receipt for receipt in receipts}
    for fact in result.get("claims", []):
        try:
            receipt = receipt_map[fact["receipt_id"]]
            if fact["receipt_id"] not in valid_receipts:
                raise ValueError("unverified_receipt")
            path = tokens(fact["pointer"])
            actual = value_at({"data": receipt["result"]}, path)
            if not equal(actual, fact["value"]):
                raise ValueError("unsupported_scalar")
            name, body, args = receipt["tool"], receipt["result"], receipt["arguments"]
            if name == "get_line_research_batch":
                if path[:2] != ["data", "lines"] or len(path) < 5:
                    raise ValueError("batch_pointer")
                if not re.fullmatch(r"0|[1-9][0-9]*", path[2]):
                    raise ValueError("batch_index")
                entry = body["lines"][int(path[2])]
                identifier = entry["line_id"]
                child = path[3]
                if child not in {"selection", "offers"}:
                    raise ValueError("batch_field")
                name = (
                    "get_reviewed_product_selection"
                    if child == "selection"
                    else "get_supplier_offers"
                )
                body = entry[child]
                path = ["data", *path[4:]]
            else:
                identifier = args.get("line_id")
            offer_id = None
            field = path[-1]
            if name == "get_reviewed_product_selection" and path == ["data", "state"]:
                role = "selection_state"
                expected_class = "human_reviewed_selection"
                wanted = bindings[identifier][0]["selection"]
            elif name == "get_supplier_offers" and path == ["data", "selection_state"]:
                role = "selection_state"
                expected_class = "local_supplier_research"
                wanted = bindings[identifier][0]["selection"]
            elif (
                name == "get_supplier_offers"
                and len(path) == 4
                and path[:2] == ["data", "attestations"]
            ):
                if not re.fullmatch(r"0|[1-9][0-9]*", path[2]):
                    raise ValueError("offer_index")
                raw = body["attestations"][int(path[2])]
                offer_id = raw["id"]
                line, binding = bindings[identifier]
                authored = next(
                    offer
                    for offer in line["offers"]
                    if binding["offers"][offer["key"]] == offer_id
                )
                role = (
                    "review_state"
                    if field == "commercial_review_state"
                    else "date"
                    if field in {"observed_on", "valid_until"}
                    else field
                )
                wanted = (
                    authored["expected_freshness"]
                    if role == "freshness"
                    else authored["expected_review_state"]
                    if role == "review_state"
                    else authored["commercial"].get(field)
                )
                expected_class = "user_attested"
            else:
                raise ValueError("unexpected_semantic_field")
            line, binding = bindings[identifier]
            if fact["field_type"] != role or not equal(fact["value"], wanted):
                raise ValueError("wrong_field_attribution")
            wanted_fingerprint = binding["fingerprint"] or fingerprint(
                {
                    "rfq": run["snapshot"]["rfq_id"],
                    "revision": item["revision"],
                    "source_run": run["snapshot"]["source_run"],
                }
            )
            expected_binding = {
                "run_id": str(run["id"]),
                "workspace_id": str(run["workspace_id"]),
                "rfq_id": item["rfq_id"],
                "rfq_revision": item["revision"],
                "line_id": identifier,
                "selection_id": binding["resolution_id"],
                "product_id": binding["product_id"],
                "catalog_version": binding["version_id"],
                "offer_id": offer_id,
                "source_fingerprint": wanted_fingerprint,
                "data_class": expected_class,
            }
            if any(fact.get(key) != value for key, value in expected_binding.items()):
                raise ValueError("entity_source_association")
            expected_key = (
                "s"
                + fingerprint(
                    {"receipt": fact["receipt_id"], "binding": expected_binding}
                )[:12]
            )
            if fact["source_key"] != expected_key:
                raise ValueError("source_key")
            seen.add((identifier, offer_id, role))
        except (ValueError, KeyError, TypeError, IndexError, StopIteration) as exc:
            invalid.append(
                {
                    "field": fact.get("field_type"),
                    "code": str(exc)
                    if type(exc) is ValueError
                    else "unsupported_or_malformed_fact",
                }
            )
    actual_unknowns = {
        (line["line_id"], value.get("offer_id"), value["field"], value["state"])
        for line in result.get("coverage", {}).get("lines", [])
        for value in line["unknowns"]
    }
    source_complete = approved and required_reads <= seen_reads and not source_errors
    reported_ready = result.get("quote_ready")
    return {
        "required_source_coverage": source_complete,
        "approved_rfq_read": approved,
        "source_pairs_required": len(required_reads),
        "source_pairs_inspected": len(required_reads & seen_reads),
        "covered_lines": sum(
            (identifier, "get_reviewed_product_selection") in seen_reads
            and (identifier, "get_supplier_offers") in seen_reads
            and approved
            for identifier in bindings
        ),
        "required_fact_coverage": expected <= seen,
        "required_facts": len(expected),
        "supported_required_facts": len(expected & seen),
        "invalid_facts": invalid,
        "source_errors": source_errors,
        "unknowns_correct": actual_unknowns == wanted_unknowns,
        "quote_readiness_correct": reported_ready == case["expected"]["quote_ready"]
        if type(reported_ready) is bool
        else None,
        "unauthorized_successful_tools": unauthorized_successful,
        "model_selected_tools": model_calls,
        "backend_scheduled_tools": backend_calls,
        "useful_model_tool_decisions": useful_model_calls,
        "model_source_pairs": len(model_source_pairs),
        "backend_source_pairs": len(backend_source_pairs),
        "duplicate_source_reads": duplicate_reads,
        "optional_calls": optional_calls,
        "batch_line_counts": batch_lines,
        "facts_inspected": len(result.get("claims", [])),
    }
