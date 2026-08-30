# Frozen implementation constraints

- Only two clinician inputs: Patient History and Current OPD Note.
- No cancer/stage/biomarker/pathway dropdowns.
- Automatic cancer detection limited to the supported 15.
- Unsupported cancer => GUIDELINE_NOT_AVAILABLE.
- Unsafe/ambiguous cancer detection => NEEDS_INFORMATION.
- Extraction may identify candidate facts only; it may never choose a guideline branch or recommendation.
- Never infer absent information as negative.
- Historical dynamic facts are not silently promoted to current facts.
- New current evidence can supersede history only when chronology/new evidence is explicit.
- Unresolved pathway-changing conflicts are passed as CONFLICT and must fail closed.
- Existing deterministic package JSONs remain untouched.
