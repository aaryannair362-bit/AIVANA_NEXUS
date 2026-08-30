from __future__ import annotations

from copy import deepcopy
from datetime import datetime
from typing import Any

SEMANTIC_UNKNOWN = {None, "UNKNOWN", "TX", "NX", "MX", "PENDING", "NOT_ASSESSED", "NOT_DONE"}
CONFLICT = object()


def _obs_status(v: Any) -> str:
    if isinstance(v, dict):
        s = str(v.get("status", "CONFIRMED")).upper()
        if s in {"CONFLICT", "CONFLICTING"}:
            return "CONFLICT"
        if s in {"UNKNOWN", "PENDING", "UNVERIFIED", "NOT_ASSESSED", "MISSING"}:
            return "UNKNOWN"
    return "CONFIRMED"


def _obs_value(v: Any) -> Any:
    return v.get("value") if isinstance(v, dict) and "value" in v else v


def _sort_key(obs: Any, idx: int):
    if not isinstance(obs, dict):
        return (0, idx)
    for k in ("observed_at", "effective_at", "date"):
        x = obs.get(k)
        if x:
            try:
                return (1, datetime.fromisoformat(str(x).replace("Z", "+00:00")).timestamp())
            except Exception:
                return (1, str(x))
    return (0, idx)


def _select_observation(raw: Any, atom: dict | None = None) -> Any:
    """Select a context/timepoint-specific observation without overwriting history.

    State facts may be scalars, structured observations, or arrays of observations.
    Decision atoms can optionally request `context` and/or `timepoint`.
    """
    atom = atom or {}
    if not isinstance(raw, list):
        return raw
    candidates = []
    for i, obs in enumerate(raw):
        if not isinstance(obs, dict):
            candidates.append((i, obs))
            continue
        if atom.get("context") is not None and obs.get("context") != atom.get("context"):
            continue
        if atom.get("timepoint") is not None and obs.get("timepoint") != atom.get("timepoint"):
            continue
        candidates.append((i, obs))
    if not candidates:
        return None
    # conflicting currently-valid observations at same requested context/timepoint fail closed.
    confirmed = [o for _, o in candidates if _obs_status(o) == "CONFIRMED" and _obs_value(o) not in SEMANTIC_UNKNOWN]
    vals = {_jsonable(_obs_value(o)) for o in confirmed}
    if len(vals) > 1 and (atom.get("context") is not None or atom.get("timepoint") is not None):
        return {"status": "CONFLICT", "value": None, "evidence": confirmed}
    candidates.sort(key=lambda x: _sort_key(x[1], x[0]))
    return candidates[-1][1]


def _jsonable(v: Any) -> str:
    try:
        import json
        return json.dumps(v, sort_keys=True, default=str)
    except Exception:
        return repr(v)


def _fact(state: dict, key: str, defs: dict, atom: dict | None = None):
    if key not in state:
        return None, "UNKNOWN"
    raw = _select_observation(state[key], atom)
    if raw is None:
        return None, "UNKNOWN"
    status = _obs_status(raw)
    if status == "CONFLICT":
        return CONFLICT, "CONFLICT"
    value = _obs_value(raw)
    d = defs.get(key, {})
    if status == "UNKNOWN" or value in set(d.get("semantic_unknown_values", [])) or value in SEMANTIC_UNKNOWN:
        return None, "UNKNOWN"
    return value, "KNOWN"


def eval_atom(atom, state, defs):
    v, status = _fact(state, atom["fact"], defs, atom)
    if status == "CONFLICT":
        return CONFLICT
    if status != "KNOWN":
        return None
    op = atom.get("op", "eq")
    t = atom.get("value")
    if op == "eq":
        return v == t
    if op == "neq":
        return v != t
    if op == "gt":
        return v > t
    if op == "gte":
        return v >= t
    if op == "lt":
        return v < t
    if op == "lte":
        return v <= t
    if op == "in":
        return v in t
    if op == "not_in":
        return v not in t
    if op == "contains":
        return t in v
    raise ValueError(op)


def eval_expr(expr, state, defs):
    if "fact" in expr:
        return eval_atom(expr, state, defs)
    if "not" in expr:
        x = eval_expr(expr["not"], state, defs)
        if x is CONFLICT:
            return CONFLICT
        return None if x is None else (not x)
    if "all" in expr:
        vals = [eval_expr(x, state, defs) for x in expr["all"]]
        if CONFLICT in vals:
            return CONFLICT
        if False in vals:
            return False
        if None in vals:
            return None
        return True
    if "any" in expr:
        vals = [eval_expr(x, state, defs) for x in expr["any"]]
        if CONFLICT in vals:
            return CONFLICT
        if True in vals:
            return True
        if None in vals:
            return None
        return False
    raise ValueError(expr)


def facts_in_expr(expr):
    if not expr:
        return []
    if "fact" in expr:
        return [expr["fact"]]
    if "not" in expr:
        return facts_in_expr(expr["not"])
    out = []
    for k in ("all", "any"):
        for x in expr.get(k, []):
            out.extend(facts_in_expr(x))
    return sorted(set(out))


def missing(expr, state, defs):
    out = []
    if "fact" in expr:
        _, status = _fact(state, expr["fact"], defs, expr)
        if status == "UNKNOWN":
            out.append(expr["fact"])
    elif "not" in expr:
        out += missing(expr["not"], state, defs)
    else:
        for k in ("all", "any"):
            for x in expr.get(k, []):
                out += missing(x, state, defs)
    return sorted(set(out))


def conflicts(expr, state, defs):
    out = []
    if "fact" in expr:
        _, status = _fact(state, expr["fact"], defs, expr)
        if status == "CONFLICT":
            out.append(expr["fact"])
    elif "not" in expr:
        out += conflicts(expr["not"], state, defs)
    else:
        for k in ("all", "any"):
            for x in expr.get(k, []):
                out += conflicts(x, state, defs)
    return sorted(set(out))


def _section_meta(pkg, codes):
    cov = pkg.get("coverage", {})
    idx = {}
    idx.update(cov.get("primary_sections", {}))
    idx.update(cov.get("supporting_sections", {}))
    out = []
    for c in codes:
        s = idx.get(c, {})
        out.append(
            {
                "code": c,
                "pages": s.get("pages", []),
                "kind": s.get("kind"),
                "source_text_sha256": s.get("source_text_sha256"),
                "found": s.get("found", False),
            }
        )
    return out


def _validate_scalar(key, v, d):
    if v is None:
        return None
    if isinstance(v, dict):
        if _obs_status(v) in {"UNKNOWN", "CONFLICT"}:
            return None
        v = _obs_value(v)
    if d.get("value_type") == "CODED" and v not in d.get("allowed_values", []):
        return f"Invalid value {v!r} for {key}"
    if d.get("value_type") == "BOOLEAN" and not isinstance(v, bool):
        return f"Invalid boolean value {v!r} for {key}"
    if d.get("value_type") == "NUMERIC" and (isinstance(v, bool) or not isinstance(v, (int, float))):
        return f"Invalid numeric value {v!r} for {key}"
    return None


def _validate_state(pkg, state, defs):
    for k, v in state.items():
        if k.startswith("__"):
            continue
        if k not in defs:
            return {"status": "INVALID_INPUT", "error": f"Unknown fact {k}"}
        d = defs[k]
        vals = v if isinstance(v, list) else [v]
        for obs in vals:
            e = _validate_scalar(k, obs, d)
            if e:
                return {"status": "INVALID_INPUT", "error": e}
    return None


def _derive_facts(pkg, state, defs):
    out = deepcopy(state)
    trace = []
    # deterministic derived facts are only filled when absent/unknown; explicit confirmed input is never overwritten.
    for rule in pkg.get("derived_rules", []):
        key = rule["target_fact"]
        existing, status = _fact(out, key, defs)
        if status == "KNOWN":
            continue
        r = eval_expr(rule["when"], out, defs)
        if r is CONFLICT:
            out[key] = {"status": "CONFLICT", "value": None, "derived_by": rule.get("id")}
            trace.append({"rule_id": rule.get("id"), "target_fact": key, "status": "CONFLICT"})
        elif r is True:
            out[key] = {"status": "CONFIRMED", "value": rule["value"], "derived": True, "derived_by": rule.get("id")}
            trace.append({"rule_id": rule.get("id"), "target_fact": key, "value": rule["value"]})
    return out, trace


def _consistency_gate(pkg, state, defs):
    triggered = []
    for rule in pkg.get("consistency_rules", []):
        try:
            r = eval_expr(rule["when"], state, defs)
        except Exception as e:
            return {"status": "RULE_ENGINE_ERROR", "error": f"consistency rule {rule.get('id')} failed: {e}"}
        if r is CONFLICT:
            triggered.append(
                {
                    "rule_id": rule.get("id"),
                    "message": rule.get("message") or "Conflicting evidence in consistency rule inputs",
                    "source_pathways": rule.get("source_pathways", []),
                    "conflicting_facts": conflicts(rule["when"], state, defs),
                }
            )
        elif r is True:
            triggered.append(
                {
                    "rule_id": rule.get("id"),
                    "message": rule.get("message"),
                    "source_pathways": rule.get("source_pathways", []),
                }
            )
    if triggered:
        return {
            "status": "REQUIRES_REVIEW",
            "reason": "CROSS_STATE_CONFLICT",
            "consistency_conflicts": triggered,
            "conflicts": triggered,
            "message": "Conflicting patient-state facts must be reconciled before a pathway result can be released.",
        }
    return None


def _decision_inventory_lookup(pkg):
    return {d.get("decision_id"): d for d in pkg.get("executable_decisions", []) if d.get("decision_id")}


def _option_filter(node, state, defs):
    rec = deepcopy(node.get("recommendation", {}))
    options = rec.get("options", [])
    shown, unknown_opts, conflict_opts = [], [], []
    for opt in options:
        expr = opt.get("applicability")
        if not expr:
            shown.append(opt)
            continue
        r = eval_expr(expr, state, defs)
        if r is CONFLICT:
            conflict_opts.append({"option_id": opt.get("option_id"), "missing_or_conflicting_facts": conflicts(expr, state, defs)})
        elif r is None:
            unknown_opts.append({"option_id": opt.get("option_id"), "missing_facts": missing(expr, state, defs), "condition": expr})
        elif r is True:
            shown.append(opt)
    rec["options"] = shown
    return rec, unknown_opts, conflict_opts


def _evidence_used(state, facts):
    out = []
    for k in sorted(set(facts)):
        if k not in state:
            continue
        raw = state[k]
        obs = _select_observation(raw, {})
        if isinstance(obs, dict):
            out.append(
                {
                    "fact_id": k,
                    "value": obs.get("value"),
                    "status": obs.get("status", "CONFIRMED"),
                    "context": obs.get("context"),
                    "timepoint": obs.get("timepoint"),
                    "evidence": obs.get("evidence") or obs.get("evidence_text"),
                }
            )
        else:
            out.append({"fact_id": k, "value": obs, "status": "CONFIRMED"})
    return out


def _what_could_change(trace, pkg, state, defs, unknown_options=None):
    inv = _decision_inventory_lookup(pkg)
    out = []
    for t in trace:
        did = t.get("decision_id")
        d = inv.get(did)
        if not d:
            continue
        for f in d.get("input_fact_ids", []):
            v, status = _fact(state, f, defs)
            out.append(
                {
                    "decision_id": did,
                    "fact_id": f,
                    "current_value": None if v is CONFLICT else v,
                    "current_status": status,
                    "alternative_branches": d.get("possible_branches", []),
                    "source_section": d.get("source_section"),
                }
            )
    for x in unknown_options or []:
        for f in x.get("missing_facts", []):
            out.append(
                {
                    "decision_id": "OPTION_APPLICABILITY",
                    "fact_id": f,
                    "current_value": None,
                    "current_status": "UNKNOWN",
                    "resulting_branch": x.get("option_id"),
                }
            )
    # dedupe compactly
    seen = set(); ded = []
    for x in out:
        key = (x.get("decision_id"), x.get("fact_id"), _jsonable(x.get("current_value")))
        if key not in seen:
            seen.add(key); ded.append(x)
    return ded


def evaluate(pkg, state):
    defs = {d["key"]: d for d in pkg["fact_definitions"]}
    bad = _validate_state(pkg, state, defs)
    if bad:
        return bad
    state, derived_trace = _derive_facts(pkg, state, defs)
    conflict = _consistency_gate(pkg, state, defs)
    if conflict:
        conflict["derived_fact_trace"] = derived_trace
        return conflict
    node_id = pkg.get("entry_point", "scope")
    trace = []
    seen = set()
    used_facts = []
    soft_missing = []
    while True:
        if node_id in seen:
            return {"status": "RULE_ENGINE_ERROR", "error": "cycle", "trace": trace}
        seen.add(node_id)
        node = pkg["nodes"].get(node_id)
        if node is None:
            return {"status": "RULE_ENGINE_ERROR", "error": f"missing node {node_id}", "trace": trace}
        if node["kind"] == "decision":
            r = eval_expr(node["expression"], state, defs)
            did = node.get("decision_id")
            fids = facts_in_expr(node["expression"]); used_facts += fids
            trace.append(
                {
                    "node_id": node_id,
                    "decision_id": did,
                    "label": node["label"],
                    "result": "CONFLICT" if r is CONFLICT else r,
                    "source_pathways": node.get("source_pathways", []),
                    "facts": fids,
                }
            )
            if r is CONFLICT:
                return {
                    "status": "REQUIRES_REVIEW",
                    "reason": "FACT_CONFLICT",
                    "conflicting_facts": conflicts(node["expression"], state, defs),
                    "conflicts": conflicts(node["expression"], state, defs),
                    "trace": trace,
                    "current_node": node_id,
                    "current_pathway": node.get("pathway_id") or pkg.get("cancer_type"),
                    "current_section": node.get("source_pathways", [None])[0] if node.get("source_pathways") else None,
                    "source_references": _section_meta(pkg, node.get("source_pathways", [])),
                }
            if r is None:
                mf = missing(node["expression"], state, defs)
                unknown_next = (node.get("on") or {}).get("UNKNOWN")
                if unknown_next:
                    soft_missing.extend(mf)
                    trace[-1]["unknown_transition_used"] = True
                    trace[-1]["missing_facts"] = mf
                    node_id = unknown_next
                    continue
                return {
                    "status": "NEEDS_INFORMATION",
                    "missing_facts": mf,
                    "missing_information": mf,
                    "trace": trace,
                    "current_node": node_id,
                    "current_pathway": node.get("pathway_id") or pkg.get("cancer_type"),
                    "current_section": node.get("source_pathways", [None])[0] if node.get("source_pathways") else None,
                    "source_pathways": node.get("source_pathways", []),
                    "source_references": _section_meta(pkg, node.get("source_pathways", [])),
                    "relevant_sections": _section_meta(pkg, node.get("source_pathways", [])),
                    "what_could_change_pathway": _what_could_change(trace, pkg, state, defs),
                    "evidence_used": _evidence_used(state, used_facts),
                    "derived_fact_trace": derived_trace,
                }
            node_id = node["on"]["TRUE" if r else "FALSE"]
            continue
        if node["kind"] == "status":
            source = node.get("source_pathways", [])
            return {
                "status": node.get("status", "OUTSIDE_ENCODED_SCOPE"),
                "terminal": node_id,
                "current_node": node_id,
                "current_pathway": node.get("pathway_id") or pkg.get("cancer_type"),
                "current_section": source[0] if source else None,
                "current_clinical_state": node.get("label"),
                "trace": trace,
                "message": node.get("label"),
                "source_pathways": source,
                "source_references": _section_meta(pkg, source),
                "relevant_sections": _section_meta(pkg, source),
                "why_this_pathway": trace,
                "missing_information": sorted(set(soft_missing)),
                "conflicts": [],
                "what_could_change_pathway": _what_could_change(trace, pkg, state, defs),
                "evidence_used": _evidence_used(state, used_facts),
                "next_transition": node.get("next_transition"),
                "derived_fact_trace": derived_trace,
            }
        if node["kind"] == "action":
            rec, unknown_opts, conflict_opts = _option_filter(node, state, defs)
            if conflict_opts:
                return {
                    "status": "REQUIRES_REVIEW",
                    "reason": "OPTION_APPLICABILITY_CONFLICT",
                    "conflicts": conflict_opts,
                    "trace": trace,
                    "current_node": node_id,
                    "current_pathway": node.get("pathway_id") or pkg.get("cancer_type"),
                }
            # If a conditional option can materially alter the exact option set, fail closed until known.
            blocking = [x for x in unknown_opts if any(o.get("option_id") == x.get("option_id") and o.get("decision_relevant", True) for o in node.get("recommendation", {}).get("options", []))]
            if blocking:
                mf = sorted({f for x in blocking for f in x.get("missing_facts", [])})
                source = list(node.get("source_pathways", []))
                return {
                    "status": "NEEDS_INFORMATION",
                    "reason": "OPTION_APPLICABILITY_UNRESOLVED",
                    "missing_facts": mf,
                    "missing_information": mf,
                    "trace": trace,
                    "current_node": node_id,
                    "current_pathway": node.get("pathway_id") or pkg.get("cancer_type"),
                    "current_section": source[0] if source else None,
                    "source_pathways": source,
                    "source_references": _section_meta(pkg, source),
                    "relevant_sections": _section_meta(pkg, source),
                    "what_could_change_pathway": _what_could_change(trace, pkg, state, defs, blocking),
                    "evidence_used": _evidence_used(state, used_facts + mf),
                    "derived_fact_trace": derived_trace,
                }
            source = list(node.get("source_pathways", []))
            support = list(rec.get("supporting_sections", []))
            codes = []
            for c in source + support:
                if c not in codes:
                    codes.append(c)
            option_facts = []
            for o in node.get("recommendation", {}).get("options", []):
                option_facts += facts_in_expr(o.get("applicability", {})) if o.get("applicability") else []
            used_facts += option_facts
            return {
                "status": "RECOMMENDATION",
                "terminal": node_id,
                "current_node": node_id,
                "current_pathway": node.get("pathway_id") or pkg.get("cancer_type"),
                "current_section": source[0] if source else None,
                "current_clinical_state": node.get("clinical_state") or node.get("label"),
                "guideline_concordant_options": rec.get("options", []),
                "recommendation_id": node.get("recommendation_id"),
                "recommendation": rec,
                "source_pathways": source,
                "supporting_sections": support,
                "source_references": _section_meta(pkg, codes),
                "relevant_sections": _section_meta(pkg, codes),
                "trace": trace,
                "why_this_pathway": trace,
                "missing_information": sorted(set(soft_missing)),
                "conflicts": [],
                "what_could_change_pathway": _what_could_change(trace, pkg, state, defs, unknown_opts),
                "evidence_used": _evidence_used(state, used_facts),
                "next_transition": rec.get("next_transition") or rec.get("next_steps", []),
                "derived_fact_trace": derived_trace,
            }
        return {"status": "RULE_ENGINE_ERROR", "error": "bad kind", "trace": trace}
