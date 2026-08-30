import asyncio,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from integration_api.taxonomy import detect_cancer
from integration_api.longitudinal import build_longitudinal_state
from integration_api.models import Observation

# no assumptions + automatic cancer detection
m=detect_cancer('', '58-year-old woman with invasive breast carcinoma. HER2 negative.')
assert m.status=='SUPPORTED' and m.cancer_type=='BREAST_CANCER',m
# unsupported cancer must not be forced
m=detect_cancer('', 'Biopsy confirms pancreatic adenocarcinoma. Seen for treatment planning.')
assert m.status=='UNSUPPORTED',m
# current progression overrides old dynamic state by not carrying old dynamic fact forward
h=[Observation(fact_id='clinical_m',value='M0',source_context='PATIENT_HISTORY',evidence_text='Stage II, M0 in 2024',temporal_scope='HISTORICAL')]
c=[Observation(fact_id='clinical_m',value='M1',source_context='CURRENT_OPD',evidence_text='PET-CT now shows M1 liver and bone metastases',temporal_scope='CURRENT')]
x=build_longitudinal_state(h,c,'BREAST_CANCER')
assert x['canonical_state']['clinical_m']['value']=='M1',x
assert x['updated_facts'] and x['superseded_facts'],x
# unresolved biomarker conflict stays conflict when chronology is not explicit
h=[Observation(fact_id='her2_status',value='NEGATIVE',source_context='PATIENT_HISTORY',evidence_text='HER2 negative',temporal_scope='HISTORICAL')]
c=[Observation(fact_id='her2_status',value='POSITIVE',source_context='CURRENT_OPD',evidence_text='HER2 positive',temporal_scope='CURRENT')]
x=build_longitudinal_state(h,c,'BREAST_CANCER')
assert x['canonical_state']['her2_status']['status']=='CONFLICT',x
# explicit repeat/new test can supersede prior value
c=[Observation(fact_id='her2_status',value='POSITIVE',source_context='CURRENT_OPD',evidence_text='New repeat biopsy now confirms HER2 positive',temporal_scope='CURRENT')]
x=build_longitudinal_state(h,c,'BREAST_CANCER')
assert x['canonical_state']['her2_status']['value']=='POSITIVE' and x['updated_facts'],x
print('INTEGRATION_PIPELINE_CORE=PASS')
