
from pathlib import Path
import shutil,sys
src=Path(__file__).resolve().parents[1]
dst=Path(sys.argv[1]).resolve() if len(sys.argv)>1 else Path.cwd()
for rel in ['backend/nexus/guidelines/encoded','knowledge']:
    s=src/rel; d=dst/rel; d.mkdir(parents=True,exist_ok=True)
    for p in s.rglob('*'):
        if p.is_file():
            out=d/p.relative_to(s); out.parent.mkdir(parents=True,exist_ok=True); shutil.copy2(p,out)
print(f'Installed full-pathway update into {dst}')
