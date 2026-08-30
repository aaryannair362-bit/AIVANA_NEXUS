from __future__ import annotations
import json
import os
import re
from typing import Any
import httpx
from .models import ExtractionBundle, Observation

UNKNOWN_TOKENS={"UNKNOWN","PENDING","NOT_ASSESSED","NOT_DONE","TX","NX","MX"}

# Integration-only normalized facts. These are clinically useful observations that
# are not yet first-class routing facts in the deterministic package schema. They
# are NEVER sent to the NEXUS rule evaluator (engine_authoritative=False).
AUXILIARY_FACT_DEFINITIONS: dict[str,dict[str,Any]] = {
    "abl1_kinase_domain_mutation": {
        "key":"abl1_kinase_domain_mutation",
        "value_type":"CODED",
        "allowed_values":["DETECTED","NOT_DETECTED","UNKNOWN"],
        "description":"ABL1 kinase-domain mutation test result/status for Ph+ ALL.",
        "applicable_guideline_ids":{"NCCN_ALL"},
        "engine_authoritative":False,
    },
    "mrd_quantitative_percent": {
        "key":"mrd_quantitative_percent",
        "value_type":"NUMERIC",
        "description":"Explicit quantitative molecular/measurable residual disease percentage.",
        "applicable_guideline_ids":{"NCCN_ALL","NCCN_AML"},
        "engine_authoritative":False,
        "unit":"%",
    },
}

# Key-specific phrases used only to recognize explicit source statements. They do
# not contain guideline decisions or recommended treatments.
ALIASES: dict[str,list[str]] = {
    "hr_status":["hormone receptor","hr status"], "her2_status":["her2"], "her2_positive":["her2"],
    "pd_l1_positive":["pd-l1","pdl1"], "pd_l1_cps_ge10":["pd-l1 cps","pdl1 cps"],
    "msi_h_dmmr":["msi-high","msi high","msi-h","dmmr","mismatch repair deficient"],
    "msi_h_dmmr_or_tmbh":["msi-high","msi high","msi-h","dmmr","tmb-high","tmb high"],
    "clinical_m":["clinical m","metastatic status","distant metast"], "clinical_n":["clinical n","nodal status"],
    "clinical_t":["clinical t","tumor t stage"], "figo_stage":["figo"], "stage_group":["stage"],
    "treatment_phase":["treatment phase","current phase","post-induction","post induction","post-consolidation","post consolidation","surveillance","relapsed","refractory","metastatic recurrence","postoperative","post-operative"],
    "response_status":["response","complete response","partial response","progressive disease","refractory","relapsed"],
    "mrd_status":["mrd","minimal residual disease","measurable residual disease"],
    "germline_brca_pathogenic":["germline brca","gbrca"], "pik3ca_mutation":["pik3ca"], "esr1_mutation":["esr1"],
    "flt3_mutation":["flt3"], "idh1_mutation":["idh1"], "idh2_mutation":["idh2"], "npm1_mutation":["npm1"],
    "tp53_mutation_or_del17p":["tp53","del17p","17p deletion"], "cd33_positive":["cd33"],
    "fgfr3_alteration":["fgfr3"], "fgfr2_fusion":["fgfr2"], "ntrk_fusion":["ntrk"], "ret_fusion":["ret fusion"],
    "braf_v600e":["braf v600e"], "kras_g12c":["kras g12c"], "idh1_mutation":["idh1"],
    "cldn18_2_positive":["cldn18.2","cldn18"], "imdc_risk":["imdc"],
    "ph_status":["philadelphia chromosome","ph status","bcr::abl1","bcr-abl1","bcr abl1"],
    "cns_involvement":["cns involvement","cns leukemia","central nervous system involvement"],
    "transplant_candidate":["transplant candidate","allogeneic transplant candidate","allo-hct candidate","allogeneic hct candidate"],
    "prior_hct":["previous allogeneic transplant","prior allogeneic transplant","prior allo-hct","previous allo-hct","allogeneic hct"],
    "abl1_kinase_domain_mutation":["abl1 kinase-domain mutation","abl1 kinase domain mutation","abl1 mutation"],
    "mrd_quantitative_percent":["mrd","minimal residual disease","measurable residual disease","bcr::abl1"],
}

DYNAMIC_KEY_PARTS=("stage","clinical_t","clinical_n","clinical_m","figo","response","mrd","phase","treatment_line","systemic_line","metastatic_line","metast","recurr","progress","margin","node","resect","operab","eligible","candid","symptom","performance","deauville","biopsy_result","prior_","ctdna")
BIOMARKER_KEY_PARTS=("her2","pd_l1","msi","tmb","brca","pik3ca","esr1","akt","pten","flt3","idh","npm1","tp53","fgfr","ntrk","ret_","braf","kras","nrg1","cldn","cd33","kmt2a")

def is_dynamic_fact(key: str) -> bool:
    k=key.lower()
    return any(x in k for x in DYNAMIC_KEY_PARTS) or any(x in k for x in BIOMARKER_KEY_PARTS)

def _extractable_fact(fd: dict[str,Any]) -> bool:
    # Cancer/package selection and guideline-derived route variables are never LLM authority.
    if fd.get("key")=="cancer_type": return False
    if fd.get("extraction_allowed") is False: return False
    if fd.get("fact_role") in {"DISPLAY_ONLY","PROVENANCE_ONLY","NON_ROUTING_CONTEXT","DERIVED_DETERMINISTIC"}: return False
    if str(fd.get("input_authority","")).upper()=="DERIVED_ONLY": return False
    return True

def _auxiliary_defs(pkg: dict[str,Any]) -> list[dict[str,Any]]:
    gid=str(pkg.get("guideline_id") or "")
    out=[]
    for fd in AUXILIARY_FACT_DEFINITIONS.values():
        if gid in fd.get("applicable_guideline_ids",set()):
            out.append(fd)
    return out

def _schema_definitions(pkg: dict[str,Any]) -> dict[str,dict[str,Any]]:
    defs={d["key"]:{**d,"engine_authoritative":True} for d in pkg.get("fact_definitions",[]) if _extractable_fact(d)}
    for fd in _auxiliary_defs(pkg): defs[fd["key"]]=fd
    return defs

def _compact_schema(pkg: dict[str,Any]) -> list[dict[str,Any]]:
    out=[]
    for fd in _schema_definitions(pkg).values():
        row={k:fd[k] for k in ("key","value_type","allowed_values","description") if k in fd}
        row["engine_authoritative"]=bool(fd.get("engine_authoritative",True))
        out.append(row)
    return out

def _json_from_text(text: str) -> Any:
    text=text.strip()
    if text.startswith("```"):
        text=re.sub(r"^```(?:json)?\s*|\s*```$","",text,flags=re.I|re.S)
    start=text.find("{"); end=text.rfind("}")
    if start>=0 and end>start: text=text[start:end+1]
    return json.loads(text)

def _coerce(value: Any, fd: dict[str,Any]) -> tuple[bool,Any]:
    vt=fd.get("value_type")
    if value is None:return True,None
    try:
        if vt=="BOOLEAN":
            if isinstance(value,bool):return True,value
            s=str(value).strip().lower()
            if s in {"true","yes","positive","present"}:return True,True
            if s in {"false","no","negative","absent"}:return True,False
            return False,None
        if vt in {"NUMERIC","INTEGER"}:
            n=float(value)
            return True,int(n) if vt=="INTEGER" else n
        if vt=="CODED":
            allowed=fd.get("allowed_values",[])
            s=str(value).strip().upper().replace("-","_").replace(" ","_")
            for a in allowed:
                if str(a).upper()==s:return True,a
            return False,None
        return True,value
    except Exception:return False,None

def _norm_evidence(s: str) -> str:
    return re.sub(r"[^a-z0-9]+"," ",(s or "").lower()).strip()

def _evidence_is_grounded(evidence: str, source_text: str) -> bool:
    e=_norm_evidence(evidence); t=_norm_evidence(source_text)
    if not e or len(e)<3: return False
    if e in t: return True
    # Conservative token-overlap allowance for punctuation/formatting differences only.
    et=[x for x in e.split() if len(x)>1]
    if len(et)<3:return False
    ts=set(t.split())
    return sum(x in ts for x in et)/len(et) >= 0.88

def validate_observations(raw: list[dict[str,Any]], pkg: dict[str,Any], source_context: str, source_text: str) -> tuple[list[Observation],list[str]]:
    defs=_schema_definitions(pkg)
    obs=[]; unresolved=[]
    for item in raw:
        key=str(item.get("fact_id") or item.get("key") or "").strip()
        if key not in defs:
            if key: unresolved.append(f"Unrecognized candidate fact: {key}")
            continue
        evidence=str(item.get("evidence_text") or "").strip()
        if not evidence:
            unresolved.append(f"{key}: rejected because no evidence text was supplied")
            continue
        if not _evidence_is_grounded(evidence,source_text):
            unresolved.append(f"{key}: rejected because evidence text could not be grounded in the supplied note")
            continue
        status=str(item.get("status") or "CONFIRMED").upper()
        if status not in {"CONFIRMED","PENDING","UNKNOWN","CONFLICT"}:status="UNKNOWN"
        ok,val=_coerce(item.get("value"),defs[key])
        if not ok:
            unresolved.append(f"{key}: value {item.get('value')!r} is outside the canonical domain")
            continue
        temporal="CURRENT" if source_context=="CURRENT_OPD" else "HISTORICAL"
        fd=defs[key]
        obs.append(Observation(fact_id=key,value=val,status=status,source_context=source_context,evidence_text=evidence,temporal_scope=temporal,observed_at=item.get("observed_at"),confidence=item.get("confidence"),engine_authoritative=bool(fd.get("engine_authoritative",True)),unit=fd.get("unit")))
    return obs,unresolved

async def _ollama_model_ready(url: str, model: str) -> tuple[bool,str | None]:
    try:
        async with httpx.AsyncClient(timeout=1.5) as client:
            r=await client.get(url.rstrip("/")+"/api/tags")
            r.raise_for_status()
            data=r.json()
        names={str(x.get("name") or x.get("model") or "") for x in data.get("models",[]) if isinstance(x,dict)}
        if model in names:
            return True,None
        # Ollama may report an explicit latest tag while config omits it.
        if ":" not in model and f"{model}:latest" in names:
            return True,None
        return False,f"Ollama is running but configured model {model!r} is not installed. Run: ollama pull {model}"
    except Exception as e:
        return False,f"Ollama is unavailable: {type(e).__name__}"


def _merge_guardrail_observations(primary: list[Observation], guardrail: list[Observation]) -> list[Observation]:
    """Merge LLM candidates with explicit-text facts without letting either silently override conflicts."""
    out=list(primary)
    seen={(o.fact_id,o.status,repr(o.value),o.evidence_text) for o in out}
    for o in guardrail:
        sig=(o.fact_id,o.status,repr(o.value),o.evidence_text)
        if sig not in seen:
            out.append(o); seen.add(sig)
    return out


async def _ollama_extract(text: str, pkg: dict[str,Any], source_context: str) -> tuple[list[Observation],list[str]]:
    url=os.getenv("NEXUS_OLLAMA_URL","http://127.0.0.1:11434").rstrip("/")
    model=os.getenv("NEXUS_OLLAMA_MODEL","medgemma:4b")
    ready,why=await _ollama_model_ready(url,model)
    if not ready:
        raise RuntimeError(why or f"Ollama model {model!r} is unavailable")
    schema=_compact_schema(pkg)
    system_prompt=(
        "You are the NEXUS clinical fact-extraction component. FACT EXTRACTION ONLY. "
        "You are not permitted to choose an NCCN pathway, node, treatment, regimen, or recommendation. "
        "Extract only facts directly supported by the supplied note and only into the supplied schema. "
        "Never infer a negative from absence. Never manufacture stage, biomarkers, eligibility, treatment phase, response, or treatment line. "
        "Preserve CURRENT versus HISTORICAL context supplied by the caller. Pending/ordered/not-resulted tests must be PENDING with null value. "
        "If wording conflicts, return CONFLICT rather than resolving it. Evidence text must be a short exact phrase copied from the note. "
        "Return JSON only."
    )
    user_prompt=f'''SOURCE_CONTEXT={source_context}\nFACT_SCHEMA={json.dumps(schema,separators=(',',':'))}\nReturn exactly {{"facts":[{{"fact_id":"...","value":...,"status":"CONFIRMED|PENDING|UNKNOWN|CONFLICT","evidence_text":"short exact supporting phrase"}}],"unresolved_mentions":["..."]}}.\nNOTE={text}'''
    timeout=float(os.getenv("NEXUS_OLLAMA_TIMEOUT","180"))
    async with httpx.AsyncClient(timeout=timeout) as client:
        r=await client.post(f"{url}/api/chat",json={"model":model,"messages":[{"role":"system","content":system_prompt},{"role":"user","content":user_prompt}],"stream":False,"format":"json","options":{"temperature":0,"num_predict":1800,"num_ctx":8192}})
        r.raise_for_status(); data=r.json(); content=data.get("message",{}).get("content","")
    obj=_json_from_text(content); facts=obj.get("facts",[]) if isinstance(obj,dict) else []
    obs,un=validate_observations(facts,pkg,source_context,text)
    un.extend(str(x) for x in (obj.get("unresolved_mentions",[]) if isinstance(obj,dict) else []))
    return obs,un

async def _gemini_extract(text: str, pkg: dict[str,Any], source_context: str) -> tuple[list[Observation],list[str]]:
    key=os.getenv("GEMINI_API_KEY","").strip()
    if not key: raise RuntimeError("GEMINI_API_KEY not set")
    model=os.getenv("GEMINI_MODEL","gemini-2.5-flash")
    schema=_compact_schema(pkg)
    prompt=f'''FACT EXTRACTION ONLY. Do not choose an NCCN pathway, scenario, route, node, treatment, regimen, or recommendation.\nExtract only explicit note-supported facts. Absence is not negative. Pending is pending.\nReturn JSON {{"facts":[{{"fact_id":"...","value":...,"status":"CONFIRMED|PENDING|UNKNOWN|CONFLICT","evidence_text":"short supporting phrase"}}],"unresolved_mentions":[]}}.\nSOURCE_CONTEXT={source_context}\nSCHEMA={json.dumps(schema,separators=(',',':'))}\nNOTE={text}'''
    endpoint=f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"
    async with httpx.AsyncClient(timeout=90) as client:
        r=await client.post(endpoint,json={"contents":[{"parts":[{"text":prompt}]}],"generationConfig":{"temperature":0,"responseMimeType":"application/json"}})
        r.raise_for_status(); data=r.json()
    content=data["candidates"][0]["content"]["parts"][0]["text"]
    obj=_json_from_text(content); obs,un=validate_observations(obj.get("facts",[]),pkg,source_context,text);un.extend(obj.get("unresolved_mentions",[]));return obs,un

def _find_span(text: str, pattern: str) -> str | None:
    m=re.search(pattern,text,re.I)
    if not m:return None
    a=max(0,m.start()-45);b=min(len(text),m.end()+70)
    return re.sub(r"\s+"," ",text[a:b]).strip()



def _first_allowed(allowed: list[Any], *candidates: Any) -> Any | None:
    for c in candidates:
        if c in allowed:
            return c
    return None


def _direct_coded_normalization(text: str, key: str, allowed: list[Any]) -> tuple[Any,str] | None:
    """Normalize explicit clinical wording into an existing package domain.

    These rules only classify facts directly stated in the source note. They do
    not select a guideline branch, regimen, or recommendation.
    """
    low=text.lower()

    # Compact TNM strings such as cT2N1M0 are common in oncology notes.
    if key == "clinical_t":
        m=re.search(r"(?:^|[^A-Za-z])c?T\s*([0-4X](?:is|mi|[a-d])?)(?=N|M|\b)",text,re.I)
        if m:
            raw="T"+m.group(1).upper()
            direct=_first_allowed(allowed,raw)
            if direct is not None:return direct,m.group(0)
            # Some packages intentionally collapse detailed T categories.
            if raw.startswith("T1") and "T1" in allowed:return "T1",m.group(0)
            if raw.startswith("T2") and "T2" in allowed:return "T2",m.group(0)
            if raw.startswith("T3") and "T3" in allowed:return "T3",m.group(0)
            if raw.startswith("T4") and "T4" in allowed:return "T4",m.group(0)
    if key == "clinical_n":
        m=re.search(r"(?:^|[^A-Za-z])N\s*([0-3X](?:[a-c])?)(?=M|\b)",text,re.I)
        if m:
            raw="N"+m.group(1).upper()
            direct=_first_allowed(allowed,raw)
            if direct is not None:return direct,m.group(0)
            if raw not in {"N0","NX"} and "N_POS" in allowed:return "N_POS",m.group(0)
    if key == "clinical_m":
        m=re.search(r"(?:^|[^A-Za-z])M\s*([01X])\b",text,re.I)
        if m:
            raw="M"+m.group(1).upper()
            direct=_first_allowed(allowed,raw)
            if direct is not None:return direct,m.group(0)
        # Explicit negative language must be checked before positive language.
        span=_find_span(text,r"\bno\b[^.!?\n]{0,120}\bdistant metastatic disease\b|\bno\b[^.!?\n]{0,120}\bdistant metastas(?:is|es)\b")
        if span and "M0" in allowed:return "M0",span
        # Do not treat phrases such as "metastatic carcinoma" in a regional node
        # as M1. Require explicit distant/organ metastases.
        span=_find_span(text,r"\b(?:distant metastas(?:is|es)|(?:liver|hepatic|bone|osseous|lung|pulmonary) metastas(?:is|es))\b")
        if span and "M1" in allowed:return "M1",span

    if key == "treatment_phase":
        phrase_map=[
            (r"\b(?:newly|recently) diagnosed\b|\binitial(?:\s+definitive)?[- ]treatment[- ]planning\b|\binitial\s+pretreatment\s+planning\b|\bseen for treatment planning\b|\bbefore (?:initiation of|any) [^.!?\n]{0,45}(?:therapy|treatment)\b|\b(?:disease )?(?:remains )?(?:active and )?untreated\b|\bprimary localized BCC\b",
             ["NEW_DIAGNOSIS","INITIAL_TREATMENT"]),
            (r"\bpost[- ]?operative\b|\bpostoperative oncology consultation\b|\b(?:three|four|six) weeks? ago\b[^.!?\n]{0,90}\b(?:resection|surgery)\b",["POSTOPERATIVE","POST_SURGERY","POST_PRIMARY"]),
            (r"\bafter adequate BCG\b|\bBCG[- ]unresponsive\b|\bfollowed by adequate BCG\b",["POST_INTRAVESICAL"]),
            (r"\bfirst[- ]line treatment planning\b|\bfirst systemic[- ]treatment planning\b",["NEW_DIAGNOSIS"]),
        ]
        for pat,cands in phrase_map:
            span=_find_span(text,pat)
            if span:
                val=_first_allowed(allowed,*cands)
                if val is not None:return val,span

    if key in {"systemic_line","metastatic_line","treatment_line"}:
        span=_find_span(text,r"\bfirst[- ]line\b|\bfirst systemic[- ]treatment\b|\bno previous systemic treatment\b|\bno prior systemic treatment\b")
        if span:
            val=_first_allowed(allowed,"FIRST")
            if val is not None:return val,span
        span=_find_span(text,r"\bsecond[- ]line\b")
        if span:
            val=_first_allowed(allowed,"SECOND","SECOND_OR_LATER")
            if val is not None:return val,span

    if key == "disease_family":
        span=_find_span(text,r"\bnon[- ]APL AML\b|\bPML::RARA\b[^.!?\n]{0,45}\bnegative\b[^.!?\n]{0,45}\bexcluding (?:acute promyelocytic leukemia|APL)\b")
        if span and "NON_APL_AML" in allowed:return "NON_APL_AML",span
        span=_find_span(text,r"\bacute promyelocytic leukemia\b|\bAPL\b")
        if span and "APL" in allowed:return "APL",span
        span=_find_span(text,r"\bBPDCN\b|\bblastic plasmacytoid dendritic cell neoplasm\b")
        if span and "BPDCN" in allowed:return "BPDCN",span

    if key == "eln_risk":
        for pat,val in [(r"\badverse[- ]risk\b|\badverse risk genetics\b","ADVERSE"),(r"\bfavorable[- ]risk\b","FAVORABLE"),(r"\bintermediate[- ]risk\b","INTERMEDIATE")]:
            span=_find_span(text,pat)
            if span and val in allowed:return val,span

    if key == "lymphoma_subtype":
        mappings=[(r"\bdiffuse large B[- ]?cell lymphoma\b|\bDLBCL\b","DLBCL"),(r"\bfollicular lymphoma\b","FOLLICULAR"),(r"\bmantle cell lymphoma\b","MANTLE_CELL"),(r"\bBurkitt lymphoma\b","BURKITT")]
        for pat,val in mappings:
            span=_find_span(text,pat)
            if span and val in allowed:return val,span

    if key == "stage_group" and ("ADVANCED" in allowed or "LIMITED" in allowed):
        m=re.search(r"\bstage\s+(I{1,3}|IV|[1-4])\b",text,re.I)
        if m:
            raw=m.group(1).upper(); advanced=raw in {"III","IV","3","4"}
            val="ADVANCED" if advanced else "LIMITED"
            if val in allowed:return val,m.group(0)

    if key == "disease_extent":
        mappings=[(r"\bprimary localized BCC\b|\blocalized basal cell carcinoma\b","LOCAL"),(r"\blocally advanced\b","LOCALLY_ADVANCED"),(r"\bnodal (?:disease|metastasis)\b","NODAL"),(r"\bdistant metastatic disease\b","METASTATIC")]
        for pat,val in mappings:
            span=_find_span(text,pat)
            if span and val in allowed:return val,span

    if key == "primary_site":
        mappings=[
            (r"\bintrahepatic cholangiocarcinoma\b","INTRAHEPATIC_CHOLANGIOCARCINOMA"),(r"\bextrahepatic cholangiocarcinoma\b","EXTRAHEPATIC_CHOLANGIOCARCINOMA"),(r"\bgallbladder (?:cancer|carcinoma)\b","GALLBLADDER"),
            (r"\banal canal\b","ANAL_CANAL"),(r"\bperianal\b","PERIANAL"),(r"\burinary bladder\b|\bbladder (?:cancer|carcinoma|lesion)\b","BLADDER"),
            (r"\bgastric gastrointestinal stromal tumor\b|\bgastric GIST\b|\boriginating from the stomach\b","STOMACH"),
        ]
        for pat,val in mappings:
            span=_find_span(text,pat)
            if span and val in allowed:return val,span

    if key == "histology":
        mappings=[
            (r"\bsquamous cell carcinoma\b","SQUAMOUS_CELL"),(r"\burothelial carcinoma\b","UROTHELIAL"),(r"\bclear[- ]cell renal cell carcinoma\b|\bclear[- ]cell RCC\b","CLEAR_CELL"),
            (r"\b(?:squamous cell carcinoma|adenocarcinoma|adenosquamous carcinoma) of (?:the )?cervix\b|\bcervical (?:squamous cell carcinoma|adenocarcinoma|adenosquamous carcinoma)\b","SQUAMOUS_ADENO_ADENOSQUAMOUS"),
            (r"\bclassical Hodgkin lymphoma\b|\bclassic Hodgkin lymphoma\b","CLASSIC_HODGKIN"),
        ]
        for pat,val in mappings:
            span=_find_span(text,pat)
            if span and val in allowed:return val,span

    if key == "diagnosis_class":
        span=_find_span(text,r"\binvasive (?:ductal|lobular)?\s*carcinoma\b")
        if span and "INVASIVE" in allowed:return "INVASIVE",span

    if key == "nmibc_risk":
        span=_find_span(text,r"\bhigh[- ]risk\b[^.!?\n]{0,35}\b(?:NMIBC|non[- ]muscle[- ]invasive)\b|\b(?:NMIBC|non[- ]muscle[- ]invasive)[^.!?\n]{0,35}\bhigh[- ]risk\b")
        if span and "HIGH" in allowed:return "HIGH",span
    if key == "bcg_exposure_state":
        span=_find_span(text,r"\bBCG[- ]unresponsive\b")
        if span and "UNRESPONSIVE" in allowed:return "UNRESPONSIVE",span

    if key == "tumor_grade":
        span=_find_span(text,r"\bhigh[- ]grade\b")
        if span and "HIGH" in allowed:return "HIGH",span
        span=_find_span(text,r"\blow[- ]grade\b")
        if span and "LOW" in allowed:return "LOW",span

    if key == "tumor_subtype":
        mappings=[(r"\bosteosarcoma\b","OSTEOSARCOMA"),(r"\bchordoma\b","CHORDOMA"),(r"\bchondrosarcoma\b","CHONDROSARCOMA"),(r"\bEwing(?:'s)? sarcoma\b","EWING_SARCOMA"),(r"\bgiant cell tumor of bone\b","GIANT_CELL_TUMOR_BONE")]
        for pat,val in mappings:
            span=_find_span(text,pat)
            if span and val in allowed:return val,span
    if key == "grade_group":
        span=_find_span(text,r"\bhigh[- ]grade\b")
        if span and "HIGH" in allowed:return "HIGH",span
        span=_find_span(text,r"\blow[- ]grade\b")
        if span and "LOW" in allowed:return "LOW",span
    if key == "location":
        span=_find_span(text,r"\b(?:distal|proximal)?\s*(?:femur|tibia|fibula|humerus|radius|ulna)\b")
        if span and "APPENDICULAR" in allowed:return "APPENDICULAR",span

    if key == "hr_status":
        span=_find_span(text,r"\bER\s*(?:0\s*%|negative)[^.!?\n]{0,45}\bPR\s*(?:0\s*%|negative)")
        if span and "NEGATIVE" in allowed:return "NEGATIVE",span
        span=_find_span(text,r"\b(?:ER|PR)\b[^.!?\n]{0,15}\b(?:positive|[1-9]\d*\s*%)\b")
        if span and "POSITIVE" in allowed:return "POSITIVE",span
    if key == "her2_status":
        span=_find_span(text,r"\bHER2\b[^.!?\n]{0,20}\b(?:IHC\s*)?3\+|\bHER2\b[^.!?\n]{0,25}\bpositive\b")
        if span and "POSITIVE" in allowed:return "POSITIVE",span
        span=_find_span(text,r"\bHER2\b[^.!?\n]{0,25}\bnegative\b")
        if span and "NEGATIVE" in allowed:return "NEGATIVE",span

    if key == "genotype":
        span=_find_span(text,r"\bKIT exon 11 mutation\b|\bimatinib[- ]sensitive KIT\b")
        if span and "KIT_PDGFRA_SENSITIVE" in allowed:return "KIT_PDGFRA_SENSITIVE",span
    if key == "prior_tki":
        span=_find_span(text,r"\bdid not receive preoperative imatinib or another TKI\b|\bno prior (?:TKI|imatinib)\b")
        if span and "NONE" in allowed:return "NONE",span

    if key == "subtype":
        mappings=[(r"\bpolycythemia vera\b|\bPV\b","POLYCYTHEMIA_VERA"),(r"\bprimary myelofibrosis\b|\bmyelofibrosis\b","MYELOFIBROSIS"),(r"\bessential thrombocyt(?:h|)emia\b|\bET\b","ESSENTIAL_THROMBOCYTHEMIA")]
        for pat,val in mappings:
            span=_find_span(text,pat)
            if span and val in allowed:return val,span
    if key == "driver_mutation":
        span=_find_span(text,r"\bJAK2(?: V617F)?\b[^.!?\n]{0,20}\bpositive\b|\bJAK2 V617F[- ]positive\b")
        if span and "JAK2" in allowed:return "JAK2",span

    return None


def _direct_boolean_normalization(text: str, key: str) -> tuple[bool,str] | None:
    # Explicit diagnosis confirmation.
    if key == "diagnosis_confirmed":
        span=_find_span(text,r"\b(?:core |excisional |needle )?biopsy\b[^.!?\n]{0,80}\b(?:confirms|confirmed|showed|shows)\b|\bflow cytometry confirmed\b")
        if span:return True,span
    if key == "intensive_induction_eligible":
        span=_find_span(text,r"\b(?:eligible|fit) for intensive induction\b|\btreating team considers (?:him|her|the patient) eligible for intensive induction\b")
        if span:return True,span
    if key == "cbf_aml":
        span=_find_span(text,r"\bcore[- ]binding[- ]factor AML\b")
        if span:return True,span
    if key == "high_risk_any":
        span=_find_span(text,r"\bhigh[- ]risk (?:BCC|basal cell)\b|\bhigh[- ]risk facial location\b")
        if span:return True,span
    if key in {"resectable","surgery_feasible","partial_nephrectomy_feasible"}:
        positive={
            "resectable":r"\b(?:technically |surgically )?resectable\b|\bpotentially resectable\b",
            "surgery_feasible":r"\b(?:technically )?resectable\b|\bmedically suitable for surgery\b|\bsurgery (?:is )?feasible\b",
            "partial_nephrectomy_feasible":r"\bpartial nephrectomy is technically feasible\b",
        }[key]
        negative=r"\b(?:currently |technically |surgically )?unresectable\b|\bno surgical option\b"
        span=_find_span(text,negative)
        if span and key=="resectable":return False,span
        span=_find_span(text,positive)
        if span:return True,span
    if key == "surgery_candidate":
        span=_find_span(text,r"\bappropriate surgical candidate\b|\bmedically fit for surgery\b|\bmedically suitable for surgery\b")
        if span:return True,span
    if key == "potentially_resectable":
        span=_find_span(text,r"\bpotentially resectable\b")
        if span:return True,span
    if key == "medically_fit":
        span=_find_span(text,r"\bmedically fit\b|\bfit for systemic therapy and gastrectomy\b")
        if span:return True,span
    if key == "performance_status_good":
        span=_find_span(text,r"\bECOG\s*[01]\b|\badequate (?:hepatic|renal|organ) function\b")
        if span:return True,span
    if key == "location_high_risk":
        span=_find_span(text,r"\bhigh[- ]risk facial location\b|\b(?:nasal ala|nasal sidewall|nose|eyelid|ear)\b")
        if span:return True,span
    if key == "aggressive_histology":
        span=_find_span(text,r"\binfiltrative basal cell carcinoma\b|\bmorpheaform\b|\baggressive histology\b")
        if span:return True,span
    if key == "poorly_defined_borders":
        span=_find_span(text,r"\bpoorly defined (?:lesion|borders?)\b")
        if span:return True,span
    if key in {"named_nerve_involvement","perineural_involvement"}:
        pat=r"\bno named[- ]nerve involvement\b" if key=="named_nerve_involvement" else r"\bno (?:clinical )?perineural (?:spread|involvement)\b"
        span=_find_span(text,pat)
        if span:return False,span
    if key == "adequate_bcg_received":
        span=_find_span(text,r"\badequate BCG\b")
        if span:return True,span
    if key == "bcg_unresponsive":
        span=_find_span(text,r"\bBCG[- ]unresponsive\b")
        if span:return True,span
    if key == "radical_cystectomy_candidate":
        span=_find_span(text,r"\b(?:fit|candidate) for radical cystectomy\b|\bradical cystectomy candidate\b")
        if span:return True,span
    if key == "cis_present":
        span=_find_span(text,r"\bcarcinoma in situ\b|\bCIS\b")
        if span:return True,span
    if key == "metastatic":
        span=_find_span(text,r"\bno\b[^.!?\n]{0,120}\bdistant metastatic disease\b|\bno\b[^.!?\n]{0,120}\b(?:pulmonary|hepatic|liver|bone|skeletal|distant) metastas(?:is|es)\b|\bdisease is localized\b")
        if span:return False,span
        span=_find_span(text,r"\bdistant metastatic disease\b|\b(?:liver|hepatic|bone|osseous|lung|pulmonary) metastas(?:is|es)\b")
        if span:return True,span
    if key == "metastatic" or key == "distant_metastases":
        pass
    if key == "distant_metastases":
        span=_find_span(text,r"\bno\b[^.!?\n]{0,120}\bdistant metastatic disease\b|\bno\b[^.!?\n]{0,120}\bdistant metastas(?:is|es)\b")
        if span:return False,span
        span=_find_span(text,r"\bdistant metastatic disease\b|\b(?:liver|hepatic|bone|osseous|lung|pulmonary) metastas(?:is|es)\b")
        if span:return True,span
    if key == "osteo_low_grade":
        span=_find_span(text,r"\bhigh[- ]grade osteosarcoma\b|\bhigh[- ]grade osteoblastic osteosarcoma\b")
        if span:return False,span
    if key == "osteo_extraskeletal":
        span=_find_span(text,r"\bosteosarcoma of (?:the )?(?:distal|proximal)?\s*(?:femur|tibia|fibula|humerus|radius|ulna)\b")
        if span:return False,span
    if key == "inflammatory":
        span=_find_span(text,r"\bno inflammatory breast changes\b")
        if span:return False,span
    if key == "postop_resection_complete":
        span=_find_span(text,r"\b(?:complete surgical resection|resection is complete)\b[^.!?\n]{0,40}\bnegative margins\b|\bcomplete surgical resection\b")
        if span:return True,span
    if key == "tumor_rupture":
        span=_find_span(text,r"\bno tumor rupture\b")
        if span:return False,span
    if key == "b_symptoms":
        span=_find_span(text,r"\bdrenching night sweats\b|\bB symptoms\b")
        if span:return True,span
    if key == "pregnant":
        span=_find_span(text,r"\b\d{1,3}[- ]year[- ]old man\b|\bmale\b")
        if span:return False,span
    if key == "age_over_60_or_unfit":
        m=re.search(r"\b(\d{1,3})[- ]year[- ]old\b",text,re.I)
        fit=_find_span(text,r"\bmedically fit\b|\bfit for curative systemic therapy\b")
        if m and int(m.group(1))<=60 and fit:return False,_find_span(text,r"\b\d{1,3}[- ]year[- ]old\b") or m.group(0)
    if key == "thrombosis_history":
        span=_find_span(text,r"\b(?:deep[- ]vein thrombosis|DVT|prior thrombosis|history of thrombosis)\b")
        if span:return True,span
    if key == "hydroxyurea_resistant_or_intolerant":
        span=_find_span(text,r"\b(?:has not|never) (?:previously )?received hydroxyurea\b|\bno prior hydroxyurea\b")
        if span:return False,span
    if key == "prior_cytoreductive_inadequate_response":
        span=_find_span(text,r"\bhas not previously received hydroxyurea, interferon, ruxolitinib, or another cytoreductive agent\b")
        if span:return False,span
    if key == "pv_high_risk":
        span=_find_span(text,r"\bhigh[- ]risk PV criteria\b|\bhigh[- ]risk polycythemia vera\b")
        if span:return True,span
    if key == "thrombosis_or_vascular_event":
        span=_find_span(text,r"\bdeep[- ]vein thrombosis\b|\bprior thrombosis\b")
        if span:return True,span
    if key == "msi_h_dmmr":
        span=_find_span(text,r"\b(?:pMMR|MMR[- ]proficient|microsatellite stable|MSS)\b")
        if span:return False,span
        span=_find_span(text,r"\b(?:dMMR|MSI[- ]H|microsatellite instability[- ]high)\b")
        if span:return True,span
    if key == "metastatic":
        span=_find_span(text,r"\bdisease is localized\b|\blocalized [^.!?\n]{0,40}primary\b")
        if span:return False,span
    return None


def _direct_numeric_normalization(text: str, key: str) -> tuple[float,str] | None:
    # Prevent substring collisions such as blast_percentage containing "age".
    if key == "age_years":
        m=re.search(r"\b(\d{1,3})[- ]year[- ]old\b|\bage\s*[:=]?\s*(\d{1,3})\b",text,re.I)
        if m:
            v=next(x for x in m.groups() if x is not None)
            return float(v),m.group(0)
    if key == "blast_percentage":
        m=re.search(r"\b(?:peripheral blood |marrow )?blasts?\s*(?:are|is|:|=)?\s*(\d+(?:\.\d+)?)\s*%",text,re.I)
        if m:return float(m.group(1)),m.group(0)
    if key == "tumor_size_cm":
        m=re.search(r"\b(?:mass|tumou?r|lesion|GIST)\b[^.!?\n]{0,40}?\b(?:measures?|measured|is)\s*(\d+(?:\.\d+)?)\s*cm\b|\b(\d+(?:\.\d+)?)\s*cm\b[^.!?\n]{0,35}\b(?:mass|tumou?r|lesion|GIST)\b",text,re.I)
        if m:
            v=next(x for x in m.groups() if x is not None);return float(v),m.group(0)
    if key == "mitotic_rate_per_5mm2":
        m=re.search(r"\b(?:high )?mitotic rate(?: of)?\s*(\d+(?:\.\d+)?)\s*mitoses? per 5\s*mm",text,re.I)
        if m:return float(m.group(1)),m.group(0)
    return None

def _explicit_coded(text: str, fd: dict[str,Any]) -> tuple[Any,str] | None:
    key=fd["key"].lower(); allowed=fd.get("allowed_values",[])
    direct=_direct_coded_normalization(text,key,allowed)
    if direct:return direct
    aliases=ALIASES.get(key,[key.replace("_"," ")])
    # Key/alias-adjacent explicit coded value.
    for a in aliases:
        for val in allowed:
            sval=str(val)
            if sval in UNKNOWN_TOKENS:continue
            words=sval.replace("_"," ").replace("/"," ")
            near=r"[^.!?\n]{0,35}"
            pat=rf"(?:{re.escape(a)}){near}\b{re.escape(words)}\b|\b{re.escape(words)}\b{near}(?:{re.escape(a)})"
            span=_find_span(text,pat)
            if span:return val,span
    # Direct MRD positivity/negativity phrases. "Detectable" means positive;
    # "undetectable/not detected" means negative. This prevents an unchanged
    # historical MRD-positive fact from being misclassified as "new today".
    if key=="mrd_status":
        span=_find_span(text,r"\b(?:MRD|minimal residual disease|measurable residual disease)\b[^.!?\n]{0,55}\b(?:undetectable|not detected|negative)\b")
        if span and "NEGATIVE" in allowed:return "NEGATIVE",span
        span=_find_span(text,r"\b(?:MRD|minimal residual disease|measurable residual disease)\b[^.!?\n]{0,55}\b(?:detectable|detected|positive)\b")
        if span and "POSITIVE" in allowed:return "POSITIVE",span
    if key=="abl1_kinase_domain_mutation":
        span=_find_span(text,r"\bABL1 kinase[- ]domain mutation\b[^.!?\n]{0,45}\b(?:not detected|negative|absent)\b")
        if span and "NOT_DETECTED" in allowed:return "NOT_DETECTED",span
        span=_find_span(text,r"\bABL1 kinase[- ]domain mutation\b[^.!?\n]{0,45}\b(?:detected|positive|identified|present)\b")
        if span and "DETECTED" in allowed:return "DETECTED",span

    # TNM codes are common and safe only for the matching explicit T/N/M key.
    if key=="clinical_m":
        m=re.search(r"\b(?:c?M)\s*([01X])\b",text,re.I)
        if m:
            val="M"+m.group(1).upper();
            if val in allowed:return val,m.group(0)
    if key=="clinical_n":
        m=re.search(r"\b(?:c?N)\s*([0-3X](?:[a-c])?)\b",text,re.I)
        if m:
            val="N"+m.group(1).upper();
            if val in allowed:return val,m.group(0)
    if key=="clinical_t":
        m=re.search(r"\b(?:c?T)\s*([0-4X](?:is|mi|[a-d])?)\b",text,re.I)
        if m:
            val="T"+m.group(1).upper();
            if val in allowed:return val,m.group(0)
    # FIGO/stage group.
    if key in {"figo_stage","stage_group"}:
        m=re.search(r"\b(?:FIGO\s+)?stage\s+([IVX]+[A-C]?[0-3]?|[0-4][A-C]?)\b",text,re.I)
        if m:
            raw=m.group(1).upper();
            for val in allowed:
                if str(val).upper()==raw:return val,m.group(0)
    # Explicit distant-metastasis language is a direct clinical M normalization,
    # not a guideline choice. Do not infer M0/M1 from absence.
    if key=="clinical_m":
        span=_find_span(text,r"\b(?:distant|liver|bone|lung) metastas(?:is|es)\b|\bmetastatic disease\b")
        if span and "M1" in allowed:return "M1",span
        span=_find_span(text,r"\bno (?:evidence of )?(?:distant )?metast(?:asis|ases|atic disease)\b")
        if span and "M0" in allowed:return "M0",span
    # Common hematologic lineage/response normalizations are direct fact normalizations, not guideline routing.
    if key=="lineage":
        m=re.search(r"\bB[- ]?(?:cell )?(?:acute lymphoblastic leukemia|ALL)\b",text,re.I)
        if m and "B_ALL" in allowed:return "B_ALL",m.group(0)
        m=re.search(r"\bT[- ]?(?:cell )?(?:acute lymphoblastic leukemia|ALL)\b",text,re.I)
        if m and "T_ALL" in allowed:return "T_ALL",m.group(0)
    if key=="response_status":
        span=_find_span(text,r"\bmorphologic(?:al)? complete remission\b|\bcomplete remission\b")
        if span:
            for candidate in ("CR","COMPLETE_RESPONSE"):
                if candidate in allowed:return candidate,span
        span=_find_span(text,r"\brefractory\b")
        if span and "REFRACTORY" in allowed:return "REFRACTORY",span
        span=_find_span(text,r"\brelapsed?\b|\brelapse\b")
        if span and "RELAPSED" in allowed:return "RELAPSED",span
    # High-level care phase explicit terms.
    if key=="treatment_phase":
        phrase_map=[
            (r"\brelapsed(?:/refractory)?|refractory|relapse\b",["RELAPSED_REFRACTORY","RELAPSED","RECURRENCE"]),
            (r"\bpost[- ]induction\b|\bafter induction\b",["POST_INDUCTION"]),(r"\bpost[- ]consolidation\b|\bafter consolidation\b",["POST_CONSOLIDATION"]),
            (r"\bsurveillance|follow[- ]up\b",["SURVEILLANCE","FOLLOW_UP"]),(r"\bpost[- ]nephrectomy\b",["POST_NEPHRECTOMY"]),
            (r"\bpost[- ]cystectomy\b",["POST_CYSTECTOMY"]),(r"\bmetastatic recurrence|distant metastatic recurrence\b",["DISTANT_METASTATIC_RECURRENCE","RECURRENT_UNRESECTABLE_METASTATIC","RELAPSED_STAGE_IV"]),
            (r"\bprogressive disease|progression\b",["PROGRESSIVE"]),(r"\bnewly diagnosed|new diagnosis|initial treatment planning\b",["NEW_DIAGNOSIS"]),
        ]
        for pat,candidates in phrase_map:
            span=_find_span(text,pat)
            if span:
                for c in candidates:
                    if c in allowed:return c,span
    return None

def _explicit_boolean(text: str, fd: dict[str,Any]) -> tuple[bool,str] | None:
    key=fd["key"].lower(); aliases=ALIASES.get(key,[key.replace("_"," ")])
    direct=_direct_boolean_normalization(text,key)
    if direct:return direct
    for a in aliases:
        # pending/ordered handled outside as PENDING.
        near=r"[^.!?\n]{0,30}"
        pos=rf"(?:{re.escape(a)}){near}\b(?:positive|present|detected|yes|eligible|candidate|resectable|operable)\b|\b(?:positive|present|detected)\b{near}(?:{re.escape(a)})"
        neg=rf"(?:{re.escape(a)}){near}\b(?:negative|absent|not detected|no|ineligible|not eligible|not a candidate|unresectable|inoperable)\b|\b(?:negative|absent|not detected|no)\b{near}(?:{re.escape(a)})"
        span=_find_span(text,neg)
        if span:return False,span
        span=_find_span(text,pos)
        if span:return True,span
    # Direct common booleans where the concept is expressed without its schema key.
    phrase_map={
        "diagnosis_confirmed": [(r"\bbiopsy[- ]confirmed\b|\bpatholog(?:y|ic) (?:confirms|confirmed)\b|\bdiagnos(?:is|ed)\b[^.!?\n]{0,45}\b(?:of|with)\b",True)],
        "cns_involvement": [(r"\bno (?:evidence of )?(?:cns|central nervous system) (?:involvement|leukemia)\b",False),(r"\b(?:cns|central nervous system) (?:involvement|leukemia) (?:is |was )?(?:present|positive|detected|confirmed)\b",True)],
        "transplant_candidate": [(r"\b(?:potential |appropriate |eligible )?(?:allogeneic |allo[- ]?)?(?:transplant|hct) candidate\b",True),(r"\bnot (?:an? )?(?:allogeneic |allo[- ]?)?(?:transplant|hct) candidate\b",False)],
        "prior_hct": [(r"\bno (?:previous|prior) (?:allogeneic |allo[- ]?)?(?:transplant|hct)\b",False),(r"\b(?:previous|prior) (?:allogeneic |allo[- ]?)?(?:transplant|hct)\b",True)],
        "distant_metastases": [(r"\b(?:liver|bone|lung|distant) metastas(?:is|es)\b",True),(r"\bno (?:distant )?metastatic disease\b",False)],
        "metastatic": [(r"\bmetastatic disease\b|\bdistant metastas(?:is|es)\b",True)],
        "local_recurrence": [(r"\blocal recurrence\b",True)],
        "postop_resection_complete": [(r"\bR0 resection\b|\bcomplete resection\b",True),(r"\bR1 resection\b|\bR2 resection\b|\bincomplete resection\b",False)],
        "residual_invasive_disease": [(r"\bresidual invasive disease\b",True),(r"\bpathologic complete response\b|\bpCR\b",False)],
    }
    for pat,val in phrase_map.get(key,[]):
        span=_find_span(text,pat)
        if span:return val,span
    return None

def _explicit_numeric(text: str, fd: dict[str,Any]) -> tuple[float,str] | None:
    key=fd["key"].lower()
    direct=_direct_numeric_normalization(text,key)
    if direct:return direct
    pats=[]
    if key=="mrd_quantitative_percent":
        pats=[
            r"\b(?:MRD|minimal residual disease|measurable residual disease|BCR::ABL1)\b[^.!?\n]{0,60}?(\d+(?:\.\d+)?)\s*%",
            r"\b(\d+(?:\.\d+)?)\s*%[^.!?\n]{0,45}\b(?:MRD|minimal residual disease|measurable residual disease|BCR::ABL1)\b",
        ]
    elif "size_cm" in key or "tumor_size" in key:pats=[r"\b(?:tumou?r|lesion|mass)\s+(?:size\s+)?(?:is\s+)?(\d+(?:\.\d+)?)\s*cm\b",r"\b(\d+(?:\.\d+)?)\s*cm\s+(?:tumou?r|lesion|mass)\b"]
    elif "depth" in key:pats=[r"\bdepth(?: of invasion)?\s*[:=]?\s*(\d+(?:\.\d+)?)\s*mm\b"]
    elif "esr" in key:pats=[r"\bESR\s*[:=]?\s*(\d+(?:\.\d+)?)\b"]
    elif "wbc" in key:pats=[r"\bWBC\s*[:=]?\s*(\d+(?:\.\d+)?)\s*(?:x?10\^?9/L|k/µL|K/uL)?"]
    elif "mitotic" in key:pats=[r"\bmitotic rate\s*[:=]?\s*(\d+(?:\.\d+)?)"]
    for pat in pats:
        m=re.search(pat,text,re.I)
        if m:return float(m.group(1)),m.group(0)
    return None

def _deterministic_extract(text: str, pkg: dict[str,Any], source_context: str) -> tuple[list[Observation],list[str]]:
    obs=[]; unresolved=[]; seen=set()
    for fd in _schema_definitions(pkg).values():
        key=fd.get("key")
        if not key:continue
        vt=fd.get("value_type")
        # Explicit pending result detection has priority over positive/negative.
        aliases=ALIASES.get(key.lower(),[key.replace("_"," ")])
        pending_span=None
        for a in aliases:
            near=r"[^.!?\n]{0,35}"
            pending_span=_find_span(text,rf"(?:{re.escape(a)}){near}\b(?:pending|ordered|awaiting|not resulted|result pending|sent)\b|\b(?:pending|awaiting)\b{near}(?:{re.escape(a)})")
            if pending_span:break
        if pending_span:
            obs.append(Observation(fact_id=key,value=None,status="PENDING",source_context=source_context,evidence_text=pending_span,temporal_scope="CURRENT" if source_context=="CURRENT_OPD" else "HISTORICAL",engine_authoritative=bool(fd.get("engine_authoritative",True)),unit=fd.get("unit")));seen.add(key);continue
        got=None
        if vt=="CODED":got=_explicit_coded(text,fd)
        elif vt=="BOOLEAN":got=_explicit_boolean(text,fd)
        elif vt in {"NUMERIC","INTEGER"}:got=_explicit_numeric(text,fd)
        if got:
            val,span=got; obs.append(Observation(fact_id=key,value=val,status="CONFIRMED",source_context=source_context,evidence_text=span,temporal_scope="CURRENT" if source_context=="CURRENT_OPD" else "HISTORICAL",engine_authoritative=bool(fd.get("engine_authoritative",True)),unit=fd.get("unit")));seen.add(key)
    return obs,unresolved

async def extract_note(text: str, pkg: dict[str,Any], source_context: str, provider: str="auto") -> tuple[list[Observation],list[str],str]:
    if not text.strip():return [],[],"none"
    requested=(provider or os.getenv("NEXUS_EXTRACTION_PROVIDER","auto")).lower()
    provider=requested
    auto_warning=None
    if provider=="auto":
        url=os.getenv("NEXUS_OLLAMA_URL","http://127.0.0.1:11434").rstrip("/")
        model=os.getenv("NEXUS_OLLAMA_MODEL","medgemma:4b")
        ready,why=await _ollama_model_ready(url,model)
        if ready:
            provider="ollama"
        elif os.getenv("GEMINI_API_KEY","").strip():
            provider="gemini"; auto_warning=why
        else:
            provider="deterministic"; auto_warning=why
    try:
        if provider=="ollama":
            o,u=await _ollama_extract(text,pkg,source_context)
            det,du=_deterministic_extract(text,pkg,source_context)
            return _merge_guardrail_observations(o,det),u+du,"ollama"
        if provider=="gemini":
            o,u=await _gemini_extract(text,pkg,source_context)
            det,du=_deterministic_extract(text,pkg,source_context)
            return _merge_guardrail_observations(o,det),u+du,"gemini"
    except Exception as e:
        o,u=_deterministic_extract(text,pkg,source_context)
        u.insert(0,f"Configured {provider} extractor unavailable; conservative explicit-only extractor used: {type(e).__name__}: {e}")
        return o,u,"deterministic_fallback"
    o,u=_deterministic_extract(text,pkg,source_context)
    if auto_warning:
        u.insert(0,f"Configured ollama extractor unavailable; conservative explicit-only extractor used: {auto_warning}")
        return o,u,"deterministic_fallback"
    return o,u,"deterministic"

