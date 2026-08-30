# NEXUS Manual Product Test Contract

This file is an executable-product constraint for this repository. Do not redesign this workflow while fixing unrelated code.

## The only manual inputs

The browser must expose only:

```text
PATIENT HISTORY / LONGITUDINAL SUMMARY
[large text box]

CURRENT OPD / CONSULTATION NOTE
[large text box]

[ RUN NEXUS ]
```

Do not add a cancer selector, stage selector, biomarker selector, structured fact form, pathway selector, or hidden manual routing step.

## Required execution pipeline

A RUN NEXUS request must actually traverse:

```text
Patient History
+
Current OPD Note
→ extract candidate clinical facts
→ normalize facts to the selected package schema
→ preserve history/current temporal context
→ calculate new / updated / superseded / conflicting facts
→ automatically classify the cancer among the 15 supported packages
→ construct the canonical current fact state
→ call the deterministic NEXUS evaluator
→ return pathway position, exact applicable options, missing information,
  conflicts, evidence, source references and possible branch-changing facts
```

The extraction model is **not** guideline authority. It may extract candidate facts such as histology, stage components, biomarkers, treatment exposure, response, MRD, margins or nodal state. It must not output or choose:

- NCCN pathway
- NCCN branch
- risk route
- treatment route
- scenario
- current guideline node
- guideline recommendation

Those are determined only by the encoded deterministic engine.

## Fail-closed extraction

Never invent a fact that is not evidenced by the supplied notes.

Example input:

```text
58-year-old woman with invasive breast carcinoma.
HER2 negative.
```

The extraction layer may capture the explicitly evidenced cancer/diagnosis/HER2 facts. It must not infer ER positivity, PR positivity, M0, postmenopausal status, node negativity or Stage II unless the text supports them.

Missing pathway-changing facts remain unknown. If the current deterministic branch cannot be resolved safely, return `NEEDS_INFORMATION`.

## Temporal semantics

A historical fact is not automatically current.

```text
HISTORY: Breast cancer diagnosed Stage II in 2024. Surgery and adjuvant treatment completed.
TODAY: PET-CT now shows liver and bone metastases.
```

The old Stage II state remains historical. The explicit current metastatic evidence must govern current-state routing. Repeated biomarkers, biopsies, treatment exposures, responses and progression assessments retain temporal context.

## Conflict semantics

Historical and current values that disagree are not silently collapsed. If a newer/repeat result is explicitly established, the old result may be recorded as superseded. If chronology/applicability is not sufficiently clear and the difference can change the pathway, send a conflict to the deterministic engine and return `REQUIRES_REVIEW` as appropriate.

## Supported cancer scope

Only these 15 packages may be classified:

1. Acute Lymphoblastic Leukemia
2. Acute Myeloid Leukemia
3. Anal Carcinoma
4. B-Cell Lymphomas
5. Basal Cell Skin Cancer
6. Biliary Tract Cancers
7. Bladder Cancer
8. Bone Cancer
9. Breast Cancer
10. Cervical Cancer
11. Gastric Cancer
12. Gastrointestinal Stromal Tumors (GIST)
13. Hodgkin Lymphoma
14. Kidney Cancer
15. Myeloproliferative Neoplasms

An explicitly unsupported primary cancer returns `GUIDELINE_NOT_AVAILABLE`. If cancer type cannot be determined safely, return `NEEDS_INFORMATION`. Never map an unsupported cancer to the closest available package.

## Required audit display

The UI must show extraction before the pathway result:

- detected cancer
- current verified facts
- current pending / unverified facts
- historical facts
- new facts from today
- updated facts
- superseded facts
- conflicting facts
- unresolved clinical mentions
- canonical facts actually sent to the deterministic engine

Then show:

- status
- detected cancer
- guideline/version
- current clinical state
- current NCCN pathway
- current pathway node
- applicable NCCN options
- required work-up / information
- missing pathway-changing facts
- conflicting information
- evidence used
- why NEXUS reached the pathway
- what could change the pathway
- source page / section references
- next transition

## Testing discipline

Do not hard-code example cases into production classification/extraction. Do not alter the 15 pathway JSONs to make manual tests pass. The UI request must reach the actual extraction/longitudinal/classification/canonical-state layers and then the exact deterministic 15-package engine.
