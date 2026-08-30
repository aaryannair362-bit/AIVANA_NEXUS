from __future__ import annotations
import re
from collections import defaultdict
from typing import Any
from .models import Observation
from .extraction import is_dynamic_fact

CLEAR_NEW_EVIDENCE=re.compile(r"\b(?:new|repeat|re[- ]biopsy|today|now|current|latest|recent|shows|demonstrates|confirms|confirmed on|updated)\b",re.I)

def _record(o: Observation) -> dict[str,Any]:
    return o.model_dump()

def _authoritative(observations: list[Observation]) -> bool:
    """Only package-defined facts are allowed into the deterministic engine state."""
    return all(x.engine_authoritative for x in observations) if observations else True

def build_longitudinal_state(history: list[Observation], current: list[Observation], cancer_type: str) -> dict[str,Any]:
    h=defaultdict(list);c=defaultdict(list)
    for o in history:h[o.fact_id].append(o)
    for o in current:c[o.fact_id].append(o)

    current_verified=[];pending=[];historical=[];new=[];updated=[];superseded=[];conflicts=[]
    non_routing=[]
    canonical: dict[str,Any]={"cancer_type":{"status":"CONFIRMED","value":cancer_type}}
    evidence_by_fact: dict[str,list[dict[str,Any]]]=defaultdict(list)

    allkeys=set(h)|set(c)
    for key in sorted(allkeys):
        hs=h.get(key,[]);cs=c.get(key,[])
        authoritative=_authoritative(hs+cs)

        historical.extend(_record(x) for x in hs)
        for x in hs:evidence_by_fact[key].append(_record(x))
        for x in cs:evidence_by_fact[key].append(_record(x))
        if not authoritative:
            non_routing.extend(_record(x) for x in hs+cs)

        cp=[x for x in cs if x.status=="PENDING"]
        if cp:
            pending.extend(_record(x) for x in cp)
            # Pending auxiliary observations remain visible but cannot alter the
            # deterministic state until a package schema/rule explicitly adopts them.
            if authoritative:
                canonical[key]={"status":"PENDING","value":None}
            continue

        cc=[x for x in cs if x.status=="CONFLICT"]
        if cc:
            conflicts.extend(_record(x) for x in cc)
            if authoritative:canonical[key]={"status":"CONFLICT","value":None}
            continue

        confirmed=[x for x in cs if x.status=="CONFIRMED"]
        if len({repr(x.value) for x in confirmed})>1:
            conflicts.extend(_record(x) for x in confirmed)
            if authoritative:canonical[key]={"status":"CONFLICT","value":None}
            continue

        cur=confirmed[-1] if confirmed else None
        hist_confirmed=[x for x in hs if x.status=="CONFIRMED"]
        old=hist_confirmed[-1] if hist_confirmed else None

        if cur:
            current_verified.append(_record(cur))
            if old is None:
                new.append(_record(cur))
                if authoritative:canonical[key]={"status":"CONFIRMED","value":cur.value}
            elif old.value==cur.value:
                # Unchanged present-day confirmation is not a "new fact".
                if authoritative:canonical[key]={"status":"CONFIRMED","value":cur.value}
            else:
                # Quantitative auxiliary observations (eg MRD 0.18% -> 0.06%)
                # are inherently new measurements when they occur in CURRENT_OPD.
                # For routing facts, require explicit chronology/new-test wording.
                explicit_update=(not authoritative) or bool(CLEAR_NEW_EVIDENCE.search(cur.evidence_text or ""))
                if explicit_update:
                    updated.append({"fact_id":key,"from":_record(old),"to":_record(cur)})
                    superseded.append(_record(old))
                    if authoritative:canonical[key]={"status":"CONFIRMED","value":cur.value}
                else:
                    conflicts.append({"fact_id":key,"historical":_record(old),"current":_record(cur),"reason":"Different values without sufficiently explicit chronology/new-test wording"})
                    if authoritative:canonical[key]={"status":"CONFLICT","value":None}
        elif old and authoritative and not is_dynamic_fact(key):
            # Durable historical facts may remain usable; dynamic stage/response/
            # biomarker/care facts are never silently carried forward as current.
            canonical[key]={"status":"CONFIRMED","value":old.value}

    return {
        "canonical_state":canonical,
        "normalized_non_routing_facts":non_routing,
        "current_verified_facts":current_verified,
        "current_pending_unverified_facts":pending,
        "historical_facts":historical,
        "new_facts_from_today":new,
        "updated_facts":updated,
        "superseded_facts":superseded,
        "conflicting_facts":conflicts,
        "evidence_by_fact":dict(evidence_by_fact),
    }
