# NEXUS — 15 Cancer Pathway Complete (Unreviewed)

This archive is the standalone deterministic NEXUS knowledge-engine package for the 15 requested guideline families.

Engineering lifecycle: `COMPLETE_UNREVIEWED`.

Safety lifecycle remains:

- `package_status = DRAFT`
- `clinical_status = REQUIRES_CLINICAL_REVIEW`
- `runtime_eligible = false`

The archive intentionally does not redistribute the source guideline PDFs or extracted verbatim page text. It retains section/page/hash provenance and the executable decision inventories.

## Verify

Run:

```bash
./VERIFY_FINAL.sh
```

The verification suite checks structural/source-page ledgers, executable-decision coverage, unused pathway-changing facts, exact option applicability, three-valued/conflict safety, numeric boundaries, enum exhaustiveness, mutation/metamorphic behavior, pairwise combinations, 10,000 structured oracle evaluations, and >10,000 randomized HTTP stability evaluations.

`COMPLETE_UNREVIEWED` is an engineering status, not clinical validation. The complete production free-text extraction → application API → frontend repository was not present in this standalone worktree, so that integration E2E is not claimed here.
