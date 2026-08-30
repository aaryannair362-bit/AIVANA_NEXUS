from __future__ import annotations
import json
import os
import sys
import hashlib
import zipfile
from pathlib import Path
from typing import Any

class EngineNotFound(RuntimeError):
    pass

COMMON_NAMES = [
    "NEXUS_15_CANCERS_ANTIGRAVITY_READY",
    "NEXUS_15_CANCERS_PATHWAY_COMPLETE_AI_ENGINEERING_REVIEWED",
    "NEXUS_15_CANCERS_ANTIGRAVITY_READY_FULL_REPO",
    "2VNCCN",
    "v1NCCN",
    "NCCN-Nexus",
    "NCCN engine",
]

COMMON_ARCHIVES = [
    "NEXUS_15_CANCERS_ANTIGRAVITY_READY_FULL_REPO.zip",
    "NEXUS_15_CANCERS_PATHWAY_COMPLETE_AI_ENGINEERING_REVIEWED.zip",
    "NEXUS_15_CANCERS_ANTIGRAVITY_READY.zip",
    "2VNCCN_CURRENT.zip",
    "2VNCCN.zip",
]

# This signature pins the audited 15-package release candidate. The original
# package provenance remains inside each JSON; these hashes include deterministic
# routing repairs validated by the free-text acceptance and regression suites.
# Requiring the inventory counts prevents the manual UI from
# silently binding to an older high-level/incomplete set of JSONs.
EXPECTED_PACKAGES: dict[str,tuple[str,str,int,str]] = {
    'nexus_acute_lymphoblastic_leukemia_v2_2026.json': ('NCCN_ALL','2.2026',70,'d77e1de05838794ae78ea7293c21c7693973e102a6534dc1dfb51c709c20d17d'),
    'nexus_acute_myeloid_leukemia_v5_2026.json': ('NCCN_AML','5.2026',111,'cb47177687129305c0a05876d68a012c51edfb04b4cf5cf2ddbce9c853addb36'),
    'nexus_anal_carcinoma_v2_2026.json': ('NCCN_ANAL','2.2026',24,'2436a3b9c66846e379ad47bebfb68bd22884863bf6556dc2bac3be0d431712dc'),
    'nexus_b_cell_lymphomas_v4_2026.json': ('NCCN_B_CELL_LYMPHOMAS','4.2026',219,'86ad8ff7d9a76f3746af4761bca5c4912738d96998a226cca003cb47ff92ca30'),
    'nexus_basal_cell_skin_cancer_v1_2027.json': ('NCCN_BASAL_CELL','1.2027',37,'30554f804985f0df34bedab360821365330b038355dcbe4fbd4cede2677d9aad'),
    'nexus_biliary_tract_cancers_v1_2026.json': ('NCCN_BILIARY','1.2026',42,'79a7a50f8b4ca514a1efd11cc75ff2900983cc00018349d5d9b048539c6bbcd6'),
    'nexus_bladder_cancer_v3_2026.json': ('NCCN_BLADDER','3.2026',61,'63c9175ea262bf206a96115d47262bd07757dc2d30640fcb85ce12c6c0b3a3f3'),
    'nexus_bone_cancer_v1_2027.json': ('NCCN_BONE','1.2027',56,'ede118b1dd04682b73e8ee6a0d9f9cb8f19bd8d592a4b53581a2105e98b28e51'),
    'nexus_breast_cancer_v6_2026.json': ('NCCN_BREAST','6.2026',92,'b76eba45df0a3e9d9e7a820f0ab0d48adbda8e69c784762da0336602ade32af7'),
    'nexus_cervical_cancer_v2_2026.json': ('NCCN_CERVICAL','2.2026',50,'5985fa2f6386e53ce47df5c42f21a0007116c7dfe085a1f1ff92d4ac389322a6'),
    'nexus_gastric_cancer_v3_2026.json': ('NCCN_GASTRIC','3.2026',48,'a10b64be422f2e7a16ce6320d959cc0e019a9e16d2a1980225eb1c182b207996'),
    'nexus_gastrointestinal_stromal_tumors_v1_2026.json': ('NCCN_GIST','1.2026',53,'18b88417aef658e7eddf3bcd1d8943beddac5687556186309cbdeb505ce24793'),
    'nexus_hodgkin_lymphoma_v2_2026.json': ('NCCN_HODGKIN','2.2026',56,'91a7dd97ce0488af4ba57bc29c1539c0c0830b43b496a3e975ea838d1e1ac958'),
    'nexus_kidney_cancer_v1_2027.json': ('NCCN_KIDNEY','1.2027',37,'91bf0d4e8589ca489cb1efc77ee773bdfbf1316d0d0876f3dfae98d6f720575d'),
    'nexus_myeloproliferative_neoplasms_v2_2026.json': ('NCCN_MPN','2.2026',28,'4c936d53dcb243a4d3552bfc0bdb673e6fd1a6df0e5430fb53da9fe48bcb14d2'),
}
EXPECTED_TOTAL_DECISIONS=sum(v[2] for v in EXPECTED_PACKAGES.values())

def _looks_like_engine(root: Path) -> bool:
    return (root / "engine" / "evaluator.py").exists() and (root / "backend" / "nexus" / "guidelines" / "encoded").is_dir()

def _find_engine_under(root: Path) -> Path | None:
    if _looks_like_engine(root): return root
    if not root.exists() or not root.is_dir(): return None
    # ZIPs normally contain one top-level repository directory. Keep this bounded.
    for child in list(root.iterdir())[:40]:
        if child.is_dir() and _looks_like_engine(child): return child
    return None

def _extract_archive(archive: Path, integration_root: Path) -> Path | None:
    try:
        digest=hashlib.sha256(archive.read_bytes()).hexdigest()[:16]
        target=integration_root/".engine_cache"/digest
        marker=target/".extracted_ok"
        if not marker.exists():
            target.mkdir(parents=True,exist_ok=True)
            with zipfile.ZipFile(archive) as z:
                # Avoid traversal; only regular repository paths are accepted.
                for member in z.infolist():
                    dest=(target/member.filename).resolve()
                    if target.resolve() not in dest.parents and dest!=target.resolve():
                        raise EngineNotFound(f"Unsafe path in engine archive: {member.filename}")
                z.extractall(target)
            marker.write_text(str(archive.resolve()))
        return _find_engine_under(target)
    except (zipfile.BadZipFile,OSError,EngineNotFound):
        return None

def locate_engine_root(integration_root: Path) -> Path:
    explicit=os.getenv("NEXUS_ENGINE_ROOT","").strip()
    candidates=[]
    if explicit:candidates.append(Path(explicit).expanduser())
    candidates.append(integration_root)
    parents=[integration_root.parent,Path.home()/"Desktop",Path.cwd().parent,Path.cwd()]
    for parent in parents:
        for name in COMMON_NAMES:candidates.append(parent/name)
    seen=set()
    for c in candidates:
        try:c=c.resolve()
        except Exception:continue
        if c in seen:continue
        seen.add(c)
        found=_find_engine_under(c)
        if found:return found

    # If the exact final engine is still present only as a ZIP on the Mac/Desktop,
    # npm run dev can consume it directly without asking the tester to unpack it.
    archives=[]
    explicit_archive=os.getenv("NEXUS_ENGINE_ARCHIVE","").strip()
    if explicit_archive:archives.append(Path(explicit_archive).expanduser())
    for parent in parents:
        for name in COMMON_ARCHIVES:archives.append(parent/name)
    seen_arch=set()
    for archive in archives:
        try:archive=archive.resolve()
        except Exception:continue
        if archive in seen_arch or not archive.is_file():continue
        seen_arch.add(archive)
        found=_extract_archive(archive,integration_root)
        if found:return found

    raise EngineNotFound(
        "Complete deterministic NEXUS engine not found. Put this integration beside your final NEXUS/2VNCCN repo or final engine ZIP, "
        "or set NEXUS_ENGINE_ROOT / NEXUS_ENGINE_ARCHIVE in .env. The UI refuses older/incomplete pathway JSONs."
    )

def _validate_final_signature(encoded: Path) -> dict[str,dict[str,Any]]:
    loaded={}; problems=[]; total=0
    for name,(expected_gid,expected_version,expected_count,expected_sha256) in EXPECTED_PACKAGES.items():
        p=encoded/name
        if not p.exists():problems.append(f"missing {name}");continue
        raw=p.read_bytes(); actual_sha256=hashlib.sha256(raw).hexdigest()
        if actual_sha256!=expected_sha256:
            problems.append(f"{name}: sha256={actual_sha256}, expected final-build hash {expected_sha256}")
        try:pkg=json.loads(raw)
        except Exception as e:problems.append(f"invalid {name}: {type(e).__name__}");continue
        gid=pkg.get("guideline_id"); version=str(pkg.get("version"))
        inv=pkg.get("executable_decisions") or []
        count=len(inv); total+=count
        if gid!=expected_gid:problems.append(f"{name}: guideline_id={gid!r}, expected {expected_gid!r}")
        if version!=expected_version:problems.append(f"{name}: version={version!r}, expected {expected_version!r}")
        if count!=expected_count:problems.append(f"{name}: executable decisions={count}, expected {expected_count}")
        if inv and any(not x.get("implemented",False) or not x.get("tested",False) for x in inv):
            problems.append(f"{name}: inventory contains unimplemented/untested source decisions")
        pc=pkg.get("lifecycle",{}).get("pathway_completeness",{})
        if pc and pc.get("status") not in {"COMPLETE_UNREVIEWED","COMPLETE_AI_ENGINEERING_REVIEWED"}:
            problems.append(f"{name}: pathway_completeness={pc.get('status')!r}")
        loaded[name]=pkg
    if total!=EXPECTED_TOTAL_DECISIONS:problems.append(f"total executable decisions={total}, expected {EXPECTED_TOTAL_DECISIONS}")
    if problems:
        raise EngineNotFound(
            "A NEXUS-looking repository was found, but it is not the final 984-decision 15-package build. "
            + "; ".join(problems[:8])
        )
    return loaded

class DeterministicEngineAdapter:
    def __init__(self,integration_root:Path):
        self.integration_root=integration_root
        self.root=locate_engine_root(integration_root)
        self.encoded=self.root/"backend"/"nexus"/"guidelines"/"encoded"
        self.packages=_validate_final_signature(self.encoded)
        if str(self.root) not in sys.path:sys.path.insert(0,str(self.root))
        from engine.evaluator import evaluate  # type: ignore
        self._evaluate=evaluate
        self.by_cancer={}
        for name,pkg in self.packages.items():
            cdef=next((d for d in pkg.get("fact_definitions",[]) if d.get("key")=="cancer_type"),None)
            for value in (cdef or {}).get("allowed_values",[]):
                if value not in {"OTHER","UNKNOWN",None}:self.by_cancer[value]=name

    @property
    def signature(self)->dict[str,Any]:
        return {"packages":len(self.packages),"executable_decisions":sum(len(p.get("executable_decisions") or []) for p in self.packages.values()),"status":"FINAL_15_PACKAGE_SIGNATURE_VERIFIED"}

    def resolve(self,cancer_type:str)->tuple[str,dict[str,Any]]:
        name=self.by_cancer.get(cancer_type)
        if not name:raise KeyError(cancer_type)
        return name,self.packages[name]

    def evaluate(self,pkg:dict[str,Any],canonical_state:dict[str,Any])->dict[str,Any]:
        return self._evaluate(pkg,canonical_state)
