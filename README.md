# NEXUS — History + OPD → RUN NEXUS

This is the **single self-contained manual-test repository**.

You do not need to place another NEXUS folder or ZIP beside it. This repository already contains:

- an engineering-audited derivative of the supplied 15-package deterministic NEXUS engine, retaining the original source provenance and 984-decision inventory;
- all 984 executable decision records;
- the free-text History + OPD integration layer;
- longitudinal current-vs-historical reconciliation;
- automatic 15-cancer detection;
- the canonical-fact bridge into the deterministic engine;
- the minimal browser UI;
- all 15 matching source guideline PDFs under `resources/guidelines/`.

## Start

Open this folder as the project root in Antigravity / VS Code / your coding environment and run only:

```bash
npm run dev
```

The launcher will:

1. find a Python runtime;
2. create `.venv` and install the small runtime requirements on first run if needed;
3. verify the exact embedded 15-package / 984-decision engine signature;
4. start the API/UI;
5. print the localhost URL;
6. open it automatically on macOS.

Default URL:

```text
http://127.0.0.1:8000
```

If port 8000 is already occupied, set `NEXUS_PORT` in `.env` before starting.

## What the browser shows

Only:

```text
PATIENT HISTORY / LONGITUDINAL SUMMARY
[large text box]

CURRENT OPD / CONSULTATION NOTE
[large text box]

[ RUN NEXUS ]
```

There is no cancer dropdown, stage dropdown, biomarker dropdown, structured-fact form, or pathway selector.

## Actual request path

```text
FREE TEXT INPUT
→ candidate clinical fact extraction
→ normalization to the selected package schema
→ historical/current separation
→ new / updated / superseded / conflicting facts
→ automatic cancer classification
→ canonical current fact state
→ deterministic NEXUS evaluator
→ pathway position + exact applicable options + missing/conflicting facts + provenance
```

The extraction layer cannot select a guideline node or recommendation. The encoded deterministic engine remains the only pathway authority.

## Extraction provider

Default `auto` behavior:

1. local Ollama, only if the server is reachable **and** the configured model is installed (`medgemma:4b` by default);
2. Gemini, if `GEMINI_API_KEY` is configured;
3. conservative explicit-only local extraction.

The fallback intentionally under-extracts rather than inventing clinical facts. Missing pathway-changing facts therefore stay missing and can produce `NEEDS_INFORMATION`.

## Useful commands

```bash
npm run doctor
npm test
npm run dev
```

`npm run doctor` verifies the pinned engineering-audited 15-package / 984-decision signature.

`npm run test:acceptance` reruns the 15 History + OPD acceptance cases supplied for manual NEXUS testing.

See `ENGINEERING_AUDIT_RELEASE_NOTES.md` for the routing/extraction repairs and full regression counts.

## Product contract

See `docs/MANUAL_TEST_PRODUCT_CONTRACT.md`. It is part of this repository's implementation constraints.

## Lifecycle

The deterministic knowledge packages remain:

```text
package_status   = DRAFT
clinical_status  = REQUIRES_CLINICAL_REVIEW
runtime_eligible = false
```

Those lifecycle flags do not prevent manual engineering testing through this localhost UI. They prevent engineering verification from being represented as independent oncologist validation or unsupervised clinical authorization.
