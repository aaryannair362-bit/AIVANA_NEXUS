#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
python3 scripts/validate_full_pathway.py .
python3 scripts/validate_executable_completeness.py .
python3 scripts/validate_mandatory_gap_coverage.py .
python3 tests/exhaustive_decision_suite.py
python3 tests/test_smoke.py
python3 tests/test_phase_safety.py
python3 tests/test_nccn_15_free_text_acceptance.py
python3 tests/pairwise_combination_suite.py
python3 tests/oracle_backed_structured_eval.py
python3 tests/realtime_http_fuzz.py
printf '\nFINAL_ARCHIVE_TEST_SUITE=PASS\n'
