#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
node tooling/doctor.mjs
npm test
python3 - <<'PY'
import hashlib,json
from pathlib import Path
root=Path('.')
man=json.loads((root/'FULL_PATHWAY_MANIFEST.json').read_text())
assert len(man['packages'])==15
for p in man['packages']:
    f=root/'resources'/'guidelines'/p['source_pdf_filename']
    assert f.exists(), f
    assert hashlib.sha256(f.read_bytes()).hexdigest()==p['source_pdf_sha256'], f
print('SOURCE_PDF_HASHES=15/15 PASS')
PY
printf '\nMANUAL_APP_VERIFICATION=PASS\n'
