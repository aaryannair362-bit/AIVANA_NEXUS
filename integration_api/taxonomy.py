from __future__ import annotations
import re
from dataclasses import dataclass

@dataclass(frozen=True)
class CancerMatch:
    cancer_type: str | None
    status: str
    evidence: list[str]

# Exact 15-cancer product scope. Long-form disease names are case-insensitive;
# short acronyms use inline case-sensitive groups so ordinary words such as
# "all" or "gist" cannot accidentally select a guideline.
SUPPORTED = {
    "ACUTE_LYMPHOBLASTIC_LEUKEMIA": [
        r"\bacute lymphoblastic leu(?:k|c)emia\b", r"\bacute lymphocytic leu(?:k|c)emia\b",
        r"(?-i:\bB[- ]?ALL\b)", r"(?-i:\bT[- ]?ALL\b)", r"(?-i:\bALL\b)"
    ],
    "ACUTE_MYELOID_LEUKEMIA": [
        r"\bacute myeloid leu(?:k|c)emia\b", r"\bacute myelogenous leu(?:k|c)emia\b",
        r"\bacute promyelocytic leu(?:k|c)emia\b", r"(?-i:\bAML\b)", r"(?-i:\bAPL\b)", r"(?-i:\bBPDCN\b)"
    ],
    "ANAL_CARCINOMA": [r"\banal canal (?:cancer|carcinoma)\b", r"\bperianal (?:cancer|carcinoma)\b", r"\banal (?:squamous cell )?carcinoma\b", r"\banal cancer\b", r"\banal canal\b[^.!?\n]{0,90}\bsquamous cell carcinoma\b", r"\bsquamous cell carcinoma\b[^.!?\n]{0,90}\banal canal\b"],
    "B_CELL_LYMPHOMA": [
        r"\bdiffuse large B[- ]?cell lymphoma\b", r"(?-i:\bDLBCL\b)", r"\bfollicular lymphoma\b",
        r"\bmantle cell lymphoma\b", r"\bmarginal zone lymphoma\b", r"\bBurkitt lymphoma\b",
        r"\bprimary mediastinal (?:large )?B[- ]?cell lymphoma\b", r"\bB[- ]?cell lymphoma\b"
    ],
    "BASAL_CELL_SKIN_CANCER": [r"\bbasal cell carcinoma\b", r"\bbasal cell skin cancer\b", r"(?-i:\bBCC\b)"],
    "BILIARY_TRACT_CANCER": [r"\bcholangiocarcinoma\b", r"\bgallbladder (?:cancer|carcinoma)\b", r"\bbiliary tract (?:cancer|carcinoma)\b", r"\bintrahepatic cholangiocarcinoma\b", r"\bextrahepatic cholangiocarcinoma\b"],
    "BLADDER_CANCER": [r"\bbladder (?:cancer|carcinoma)\b", r"\burothelial carcinoma of (?:the )?bladder\b", r"\bupper tract urothelial carcinoma\b", r"(?-i:\bUTUC\b)"],
    "BONE_CANCER": [r"\bosteosarcoma\b", r"\bEwing(?:'s)? sarcoma\b", r"\bchondrosarcoma\b", r"\bchordoma\b", r"\bgiant cell tumor of bone\b", r"\bbone sarcoma\b"],
    "BREAST_CANCER": [r"\bbreast (?:cancer|carcinoma)\b", r"\binvasive (?:ductal|lobular)?\s*carcinoma of (?:the )?breast\b", r"\bductal carcinoma in situ\b", r"(?-i:\bDCIS\b)"],
    "CERVICAL_CANCER": [r"\bcervical (?:cancer|carcinoma)\b", r"\bcarcinoma of (?:the )?cervix\b", r"\bcervix (?:cancer|carcinoma)\b"],
    "GASTRIC_CANCER": [r"\bgastric (?:cancer|carcinoma|adenocarcinoma)\b", r"\bstomach (?:cancer|carcinoma|adenocarcinoma)\b"],
    "GIST": [r"\bgastrointestinal stromal tumou?r\b", r"(?-i:\bGIST\b)"],
    "HODGKIN_LYMPHOMA": [r"\bHodgkin(?:'s)? lymphoma\b", r"\bclassical Hodgkin lymphoma\b", r"\bnodular lymphocyte[- ]predominant Hodgkin lymphoma\b", r"(?-i:\bNLPHL\b)"],
    "KIDNEY_CANCER": [r"\bkidney (?:cancer|carcinoma)\b", r"\brenal cell carcinoma\b", r"(?-i:\bRCC\b)"],
    "MYELOPROLIFERATIVE_NEOPLASM": [r"\bmyeloproliferative neoplasm\b", r"\bpolycythemia vera\b", r"\bessential thrombocyth(?:a|e)emia\b", r"\bmyelofibrosis\b", r"(?-i:\bMPN\b)"],
}

# Common explicit unsupported primaries. If the current note names one and no
# supported current primary is named, do not fall back to a historical supported
# cancer and do not force it into the nearest package.
UNSUPPORTED = [
    r"\blung (?:cancer|carcinoma|adenocarcinoma)\b", r"\bnon[- ]small cell lung cancer\b", r"\bsmall cell lung cancer\b",
    r"\bprostate (?:cancer|carcinoma|adenocarcinoma)\b", r"\bovarian (?:cancer|carcinoma)\b",
    r"\bcolorectal (?:cancer|carcinoma)\b", r"\bcolon (?:cancer|carcinoma|adenocarcinoma)\b", r"\brectal (?:cancer|carcinoma|adenocarcinoma)\b",
    r"\bpancreatic (?:cancer|carcinoma|adenocarcinoma)\b", r"\bpancreas (?:cancer|carcinoma|adenocarcinoma)\b",
    r"\bhepatocellular carcinoma\b", r"(?-i:\bHCC\b)", r"\bmelanoma\b", r"\bhead and neck cancer\b",
    r"\besophageal (?:cancer|carcinoma|adenocarcinoma)\b", r"\bthyroid (?:cancer|carcinoma)\b", r"\bmultiple myeloma\b",
    r"\bchronic myeloid leu(?:k|c)emia\b", r"(?-i:\bCML\b)", r"\bchronic lymphocytic leu(?:k|c)emia\b", r"(?-i:\bCLL\b)",
]

def _supported_hits(text: str, prefix: str) -> tuple[dict[str,int],dict[str,list[str]]]:
    scores={k:0 for k in SUPPORTED}; ev={k:[] for k in SUPPORTED}
    for cancer,patterns in SUPPORTED.items():
        seen_spans=set()
        for pat in patterns:
            for m in re.finditer(pat,text or "",re.I):
                span=(m.start(),m.end())
                # Overlapping long-form + acronym aliases should count once.
                if span in seen_spans: continue
                seen_spans.add(span); scores[cancer]+=1; ev[cancer].append(f"{prefix}: {m.group(0)}")
    return scores,ev

def _unsupported_hits(text: str, prefix: str) -> list[str]:
    out=[]
    for pat in UNSUPPORTED:
        for m in re.finditer(pat,text or "",re.I): out.append(f"{prefix}: {m.group(0)}")
    return out[:8]

def _winner(scores: dict[str,int]) -> list[str]:
    m=max(scores.values()) if scores else 0
    return [k for k,v in scores.items() if m>0 and v==m]

def detect_cancer(patient_history: str, current_opd_note: str) -> CancerMatch:
    # Current encounter is authoritative for active disease identification.
    cs,ce=_supported_hits(current_opd_note,"CURRENT_OPD")
    current_supported=_winner(cs)
    current_unsupported=_unsupported_hits(current_opd_note,"CURRENT_OPD")
    if current_unsupported and not current_supported:
        return CancerMatch(None,"UNSUPPORTED",current_unsupported)
    if current_unsupported and current_supported:
        return CancerMatch(None,"AMBIGUOUS",sum((ce[x][:3] for x in current_supported),[])+current_unsupported)
    if len(current_supported)==1:
        return CancerMatch(current_supported[0],"SUPPORTED",ce[current_supported[0]][:8])
    if len(current_supported)>1:
        return CancerMatch(None,"AMBIGUOUS",sum((ce[x][:3] for x in current_supported),[]))

    # If today's note does not name a primary, a single explicit historical cancer
    # can establish which package owns the episode. It does not promote historical
    # stage/biomarkers to current facts.
    hs,he=_supported_hits(patient_history,"PATIENT_HISTORY")
    historical_supported=_winner(hs)
    historical_unsupported=_unsupported_hits(patient_history,"PATIENT_HISTORY")
    if historical_unsupported and not historical_supported:
        return CancerMatch(None,"UNSUPPORTED",historical_unsupported)
    if len(historical_supported)==1:
        return CancerMatch(historical_supported[0],"SUPPORTED",he[historical_supported[0]][:8])
    if len(historical_supported)>1 or (historical_unsupported and historical_supported):
        return CancerMatch(None,"AMBIGUOUS",sum((he[x][:3] for x in historical_supported),[])+historical_unsupported)
    return CancerMatch(None,"NOT_DETECTED",[])
