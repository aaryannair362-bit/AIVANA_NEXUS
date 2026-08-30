from __future__ import annotations
from typing import Any, Literal
from pydantic import BaseModel, Field

FactStatus = Literal["CONFIRMED", "PENDING", "UNKNOWN", "CONFLICT"]
SourceContext = Literal["PATIENT_HISTORY", "CURRENT_OPD"]

class RunNexusRequest(BaseModel):
    patient_history: str = Field(default="", max_length=200_000)
    current_opd_note: str = Field(default="", max_length=100_000)

class Observation(BaseModel):
    fact_id: str
    value: Any = None
    status: FactStatus = "CONFIRMED"
    source_context: SourceContext
    evidence_text: str
    temporal_scope: Literal["HISTORICAL", "CURRENT", "UNRESOLVED"]
    observed_at: str | None = None
    confidence: float | None = None
    # True only for facts defined by the deterministic guideline package.
    # Auxiliary normalized clinical observations are deliberately excluded from
    # the deterministic engine input even though they remain visible/auditable.
    engine_authoritative: bool = True
    unit: str | None = None

class ExtractionBundle(BaseModel):
    detected_cancer: str | None = None
    detection_status: Literal["SUPPORTED", "AMBIGUOUS", "UNSUPPORTED", "NOT_DETECTED"] = "NOT_DETECTED"
    detection_evidence: list[str] = Field(default_factory=list)
    provider: str = "deterministic"
    observations: list[Observation] = Field(default_factory=list)
    unresolved_clinical_mentions: list[str] = Field(default_factory=list)
