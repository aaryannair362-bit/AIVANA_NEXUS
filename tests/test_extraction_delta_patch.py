from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from integration_api.models import RunNexusRequest
from integration_api.orchestrator import NexusOrchestrator

HISTORY = """32-year-old male diagnosed 4 months ago with B-cell acute lymphoblastic leukemia. Bone marrow at diagnosis showed 88% lymphoblasts. Flow cytometry was consistent with B-ALL. Cytogenetic/molecular testing demonstrated BCR::ABL1 fusion consistent with Philadelphia chromosome-positive B-ALL. No CNS involvement was identified at diagnosis.
Patient received frontline induction containing a tyrosine kinase inhibitor with ALL-directed therapy. Bone marrow after induction showed morphologic complete remission. MRD testing after induction remained detectable at 0.18%. Patient has an HLA-matched sibling and has previously been assessed as a potential allogeneic transplant candidate. No previous allogeneic transplant."""

CURRENT = """Patient presents following repeat bone marrow and MRD assessment after additional therapy. He is clinically stable with ECOG 1. CBC shows Hb 10.8 g/dL, platelets 156,000/µL, ANC 2,100/µL.
Bone marrow demonstrates continued morphologic complete remission. Current molecular MRD remains positive with BCR::ABL1 detectable at 0.06%. No new neurologic symptoms and no evidence of CNS leukemia. ABL1 kinase-domain mutation testing has been sent and is pending."""


def fact(records, fact_id):
    return [x for x in records if x.get("fact_id") == fact_id]


async def _run():
    # Force conservative extraction so this regression does not require Ollama/Gemini.
    os.environ["NEXUS_EXTRACTION_PROVIDER"] = "deterministic"
    return await NexusOrchestrator(ROOT).run(
        RunNexusRequest(patient_history=HISTORY, current_opd_note=CURRENT)
    )


def test_b_all_longitudinal_regression():
    out = asyncio.run(_run())
    ex = out["extraction"]
    nx = out["nexus_result"]

    assert ex["detected_cancer"] == "ACUTE_LYMPHOBLASTIC_LEUKEMIA"
    assert nx["status"] == "NEEDS_INFORMATION"
    assert "treatment_phase" in nx["missing_pathway_changing_facts"]

    # Historical and current MRD status are both positive. It must NOT be called new.
    assert fact(ex["historical_facts"], "mrd_status")[0]["value"] == "POSITIVE"
    assert fact(ex["current_verified_facts"], "mrd_status")[0]["value"] == "POSITIVE"
    assert not fact(ex["new_facts_from_today"], "mrd_status")

    # Quantitative MRD changes are preserved as a delta without becoming routing authority.
    q = fact(ex["updated_facts"], "mrd_quantitative_percent")
    assert len(q) == 1
    assert q[0]["from"]["value"] == 0.18
    assert q[0]["to"]["value"] == 0.06
    assert q[0]["to"]["engine_authoritative"] is False

    # ABL1 pending is normalized, visible, and explicitly excluded from engine authority.
    abl1 = fact(ex["current_pending_unverified_facts"], "abl1_kinase_domain_mutation")
    assert len(abl1) == 1
    assert abl1[0]["status"] == "PENDING"
    assert abl1[0]["value"] is None
    assert abl1[0]["engine_authoritative"] is False
    assert "abl1_kinase_domain_mutation" not in ex["canonical_facts_sent_to_engine"]

    # Quantitative MRD is audit/display information only until the deterministic package adopts it.
    assert "mrd_quantitative_percent" not in ex["canonical_facts_sent_to_engine"]

    # Fallback mode must never be silent.
    assert ex["extraction_mode_warning"]


if __name__ == "__main__":
    test_b_all_longitudinal_regression()
    print("EXTRACTION_DELTA_PATCH_REGRESSION=PASS")
