# Extraction/longitudinal patch applied

This snapshot includes the History+OPD extraction/delta patch validated against the supplied Ph+ B-ALL case.

Changes are limited to:

- `integration_api/models.py`
- `integration_api/extraction.py`
- `integration_api/longitudinal.py`
- `integration_api/orchestrator.py`
- `frontend/index.html`
- `tests/test_extraction_delta_patch.py`

The 15 deterministic NCCN JSON packages are byte-for-byte unchanged from the pre-patch repository.

Run:

```bash
python3 tests/test_extraction_delta_patch.py
npm run dev
```

Expected regression status for the supplied case remains `NEEDS_INFORMATION` with missing `treatment_phase`; the patch improves extraction/audit quality without fabricating that phase.
