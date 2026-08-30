# NEXUS 15-Cancer History + OPD — Engineering Audited Release Candidate

## Runtime contract

Manual product input remains exactly:

1. Patient History / Longitudinal Summary
2. Current OPD / Consultation Note
3. RUN NEXUS

No cancer, stage, biomarker, or pathway dropdown is required. Cancer detection and fact extraction happen before the deterministic pathway evaluator.

## LLM boundary

Ollama/MedGemma or Gemini may be used only to extract schema-valid candidate facts from the supplied note. The LLM is explicitly prohibited from choosing an NCCN pathway, node, regimen, treatment, or recommendation. Validated LLM observations are merged with a conservative explicit-text extractor; conflicts remain conflicts. The final pathway result is produced only by `engine/evaluator.py` and the encoded deterministic package.

Ollama readiness now verifies both the server and the configured model via `/api/tags`. If `medgemma:4b` is not installed, the UI/API reports the fallback instead of silently implying LLM extraction succeeded.

## Acceptance repairs

The 15 hypothetical History + OPD cases supplied for product testing are now stored in `tests/nccn_15_acceptance_cases.json` and tested by `tests/test_nccn_15_free_text_acceptance.py`.

Repairs were made at the correct layer rather than hard-coding case answers:

- extraction normalization for explicit oncology terminology, TNM/FIGO, disease subtype, treatment phase, and negative-metastasis language;
- age/blast-percentage substring collision removal;
- three-valued UNKNOWN transitions for safe high-level pathway release while retaining missing refinement facts;
- option-level modifiers no longer suppress an already-established pathway when unconditional options are available;
- Breast `preoperative_systemic_indicated` was removed as an extractor-controlled routing fact and replaced by deterministic receptor + clinical T/N criteria;
- exhaustive test harness now explicitly tests encoded UNKNOWN branches and semantic-unknown values under the same three-valued runtime semantics.

## Current engineering verification

- Cancer packages: 15
- Executable decisions: 984/984 implemented and tested
- Free-text acceptance cases: 15/15 expected recommendation-level directions
- Structural packages: 15/15 PASS
- Mandatory-gap coverage: 15/15 PASS
- Exhaustive decision refs: 984/984 PASS
- Pairwise cases: 2,551; failures 0
- Structured oracle evaluations: 10,000; failures 0
- HTTP fuzz requests: 11,281; engine errors 0
- Consistency rules: 31/31

## Important status

This remains an engineering-audited `COMPLETE_UNREVIEWED` package. Lifecycle status remains `DRAFT / REQUIRES_CLINICAL_REVIEW / runtime_eligible=false` for clinical deployment. Engineering verification is not independent oncologist validation or autonomous prescribing authorization.
