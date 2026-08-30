from __future__ import annotations
from pathlib import Path
from typing import Any
from .models import RunNexusRequest
from .taxonomy import detect_cancer
from .engine_adapter import DeterministicEngineAdapter, EngineNotFound
from .extraction import extract_note
from .longitudinal import build_longitudinal_state


def _source_refs(pkg: dict[str,Any], result: dict[str,Any]) -> list[dict[str,Any]]:
    refs=[]; seen=set()
    sections=[]
    raw=result.get("source_references") or result.get("source_pathways") or []
    for x in raw:
        if isinstance(x,str):sections.append(x)
        elif isinstance(x,dict):
            sec=x.get("section") or x.get("page_label")
            if sec:sections.append(sec)
    nid=result.get("current_node") or result.get("terminal")
    node=pkg.get("nodes",{}).get(nid,{})
    sections += list(node.get("source_pathways") or [])
    for opt in result.get("guideline_concordant_options") or []:
        pr=opt.get("source_provenance") or {}
        sec=pr.get("section") or pr.get("page_label")
        if sec:sections.append(sec)
    cov=pkg.get("coverage",{})
    for sec in sections:
        if sec in seen:continue
        seen.add(sec); meta={}
        for group in ("primary_sections","supporting_sections"):
            if sec in cov.get(group,{}):meta=cov[group][sec];break
        refs.append({"section":sec,"physical_pages":meta.get("physical_pages") or meta.get("pages") or [],"source_anchor":meta.get("source_anchor"),"guideline":pkg.get("title"),"version":pkg.get("version")})
    return refs

class NexusOrchestrator:
    def __init__(self, integration_root: Path):
        self.integration_root=integration_root
        self._adapter: DeterministicEngineAdapter | None=None

    def adapter(self) -> DeterministicEngineAdapter:
        if self._adapter is None:self._adapter=DeterministicEngineAdapter(self.integration_root)
        return self._adapter

    async def run(self, req: RunNexusRequest) -> dict[str,Any]:
        cancer=detect_cancer(req.patient_history,req.current_opd_note)
        extraction_base={
            "detected_cancer":cancer.cancer_type,
            "cancer_detection_status":cancer.status,
            "cancer_detection_evidence":cancer.evidence,
            "current_verified_facts":[],"current_pending_unverified_facts":[],"historical_facts":[],
            "new_facts_from_today":[],"updated_facts":[],"superseded_facts":[],"conflicting_facts":[],
            "unresolved_clinical_mentions":[],"provider_warnings":[],"normalized_non_routing_facts":[],"canonical_facts_sent_to_engine":{},
        }
        if cancer.status=="UNSUPPORTED":
            return {"extraction":extraction_base,"nexus_result":{"status":"GUIDELINE_NOT_AVAILABLE","detected_cancer":None,"message":"The note describes a cancer outside the currently supported 15-package NEXUS scope."}}
        if cancer.status in {"AMBIGUOUS","NOT_DETECTED"} or not cancer.cancer_type:
            return {"extraction":extraction_base,"nexus_result":{"status":"NEEDS_INFORMATION","detected_cancer":None,"message":"Cancer type cannot be determined safely from the supplied notes."}}
        try:
            adapter=self.adapter(); package_name,pkg=adapter.resolve(cancer.cancer_type)
        except EngineNotFound as e:
            return {"extraction":extraction_base,"nexus_result":{"status":"ENGINE_NOT_AVAILABLE","message":str(e)}}
        except KeyError:
            return {"extraction":extraction_base,"nexus_result":{"status":"GUIDELINE_NOT_AVAILABLE","detected_cancer":cancer.cancer_type}}

        hobs,hun,hprovider=await extract_note(req.patient_history,pkg,"PATIENT_HISTORY")
        cobs,cun,cprovider=await extract_note(req.current_opd_note,pkg,"CURRENT_OPD")
        merged=build_longitudinal_state(hobs,cobs,cancer.cancer_type)
        # Any unresolved same-fact conflict is explicitly sent to the deterministic engine.
        result=adapter.evaluate(pkg,merged["canonical_state"])
        source_refs=_source_refs(pkg,result)
        current_state={k:v for k,v in merged["canonical_state"].items() if k in {"treatment_phase","clinical_t","clinical_n","clinical_m","figo_stage","stage_group","disease_extent","response_status","systemic_line","metastatic_line","histology","primary_site"}}
        all_unresolved=hun+cun
        provider_warnings=[x for x in all_unresolved if str(x).startswith("Configured ")]
        clinical_unresolved=[x for x in all_unresolved if x not in provider_warnings]
        fallback_active=any(p in {"deterministic","deterministic_fallback"} for p in (hprovider,cprovider))
        extraction={**extraction_base,
            "provider":{"history":hprovider,"current_opd":cprovider},
            "provider_warnings":provider_warnings,
            "current_verified_facts":merged["current_verified_facts"],
            "current_pending_unverified_facts":merged["current_pending_unverified_facts"],
            "historical_facts":merged["historical_facts"],
            "new_facts_from_today":merged["new_facts_from_today"],
            "updated_facts":merged["updated_facts"],
            "superseded_facts":merged["superseded_facts"],
            "conflicting_facts":merged["conflicting_facts"],
            "normalized_non_routing_facts":merged.get("normalized_non_routing_facts",[]),
            "unresolved_clinical_mentions":clinical_unresolved,
            "extraction_mode_warning": ("Conservative explicit-only extraction is active because the configured AI extractor was unavailable or not selected. Deterministic NEXUS routing remains active, but extraction recall may be lower than the product-like LLM extraction mode." if fallback_active else None),
            "canonical_facts_sent_to_engine":merged["canonical_state"],
        }
        nexus={
            "status":result.get("status"),
            "detected_cancer":cancer.cancer_type,
            "guideline":pkg.get("title") or pkg.get("guideline_id"),
            "guideline_id":pkg.get("guideline_id"),
            "guideline_version":pkg.get("version"),
            "package_file":package_name,
            "current_clinical_state":result.get("current_clinical_state") or current_state,
            "current_nccn_pathway":result.get("current_pathway") or result.get("pathway_id") or result.get("current_section"),
            "current_pathway_node":result.get("current_node") or result.get("terminal"),
            "applicable_nccn_options":result.get("guideline_concordant_options") or result.get("options") or [],
            "required_workup_information":result.get("required_workup") or [],
            "missing_pathway_changing_facts":result.get("missing_information") or [],
            "conflicting_information":result.get("conflicts") or result.get("conflicting_facts") or merged["conflicting_facts"],
            "evidence_used":merged["evidence_by_fact"],
            "why_nexus_reached_this_pathway":result.get("why_this_pathway") or result.get("trace") or [],
            "what_could_change_the_pathway":result.get("what_could_change_pathway") or [],
            "source_page_section_references":source_refs,
            "next_transition":result.get("next_transition") or result.get("next_steps") or [],
            "raw_deterministic_response":result,
        }
        return {"extraction":extraction,"nexus_result":nexus}
