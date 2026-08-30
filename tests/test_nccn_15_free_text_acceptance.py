from __future__ import annotations

import json
import os
import sys
from pathlib import Path

# This suite is intentionally deterministic so it can run on a coder's machine
# without requiring Ollama/Gemini. The same canonical facts then enter the real
# deterministic 15-package NEXUS evaluator.
os.environ['NEXUS_EXTRACTION_PROVIDER'] = 'deterministic'

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient  # noqa: E402
from integration_api.app import app  # noqa: E402

CASES = json.loads((ROOT / 'tests' / 'nccn_15_acceptance_cases.json').read_text())
client = TestClient(app)

failures = []
for case in CASES:
    response = client.post(
        '/api/v1/nexus/run',
        json={
            'patient_history': case['patient_history'],
            'current_opd_note': case['current_opd_note'],
        },
    )
    if response.status_code != 200:
        failures.append(f"case {case['case']}: HTTP {response.status_code}")
        continue
    data = response.json()
    extraction = data.get('extraction', {})
    result = data.get('nexus_result', {})
    option_ids = {o.get('option_id') for o in result.get('applicable_nccn_options', [])}

    checks = {
        'cancer': extraction.get('detected_cancer') == case['expected_cancer'],
        'status': result.get('status') == case['expected_status'],
        'node': result.get('current_pathway_node') == case['expected_node'],
        'required_options': set(case.get('required_option_ids', [])).issubset(option_ids),
    }
    bad = [k for k, ok in checks.items() if not ok]
    if bad:
        failures.append(
            f"case {case['case']} {case['name']}: failed {bad}; "
            f"cancer={extraction.get('detected_cancer')!r} "
            f"status={result.get('status')!r} "
            f"node={result.get('current_pathway_node')!r} "
            f"options={sorted(x for x in option_ids if x)}"
        )

# Explicit fail-closed refinements that must remain unknown rather than be invented.
case2 = client.post('/api/v1/nexus/run', json={
    'patient_history': CASES[1]['patient_history'],
    'current_opd_note': CASES[1]['current_opd_note'],
}).json()['nexus_result']
assert 'tp53_mutation_or_del17p' in case2.get('missing_pathway_changing_facts', []), case2

case10 = client.post('/api/v1/nexus/run', json={
    'patient_history': CASES[9]['patient_history'],
    'current_opd_note': CASES[9]['current_opd_note'],
}).json()['nexus_result']
assert 'para_aortic_nodes_positive' in case10.get('missing_pathway_changing_facts', []), case10

if failures:
    raise AssertionError('\n'.join(failures))

print(f'NCCN_15_FREE_TEXT_ACCEPTANCE=PASS cases={len(CASES)}/15')
